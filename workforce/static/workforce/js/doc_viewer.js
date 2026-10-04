/* Purpose: The driver-document popup — scan viewer with crop/rotate, number + expiry fields, Submit-on-change, staff Verify / Undo.
   Used by: workforce/crm/lead_detail.html (CRM driver lead) and workforce/driver_detail.html (driver record), with
            workforce/parts/_doc_viewer_modal.html + _doc_viewer_attrs.html.
   Notes: Config from window.DOC_VIEWER_CONFIG (or the CRM page's CRMD_CONFIG): urlDocEditBase ("/workforce/drivers/<id>/document/"), csrfToken.
          Any element with data-doc-open (or .crmdoc__row) + the data-doc-* attributes opens it. Needs Cropper.js and Bootstrap. */
(function () {
  'use strict';

  function cfg() { return window.DOC_VIEWER_CONFIG || window.CRMD_CONFIG || {}; }

  // Every opener carries its own facts in data-*, so opening the viewer costs no
  // second request. Elements are looked up at click time, never cached: HTMX
  // replaces this markup on navigation and a cached node would be detached.
  var docShown = null;   // the row the viewer is currently showing
  var docSide = 'front';

  function docModal(id) {
    var el = document.getElementById(id);
    if (!el || !window.bootstrap) return null;
    return bootstrap.Modal.getOrCreateInstance(el);
  }

  function docFact(list, label, value) {
    if (!value) return;
    var dt = document.createElement('dt');
    dt.textContent = label;
    var dd = document.createElement('dd');
    dd.textContent = value;
    list.appendChild(dt);
    list.appendChild(dd);
  }

  // Paint one side of the open document. `side` falls back to whichever side
  // actually has a file, so a back-only row never opens on a blank stage.
  function docPaintSide(side) {
    if (!docShown) return;
    docStopCropper();
    var d = docShown;
    var url = side === 'back' ? d.docBack : d.docFront;
    if (!url) { side = side === 'back' ? 'front' : 'back'; url = side === 'back' ? d.docBack : d.docFront; }
    docSide = side;
    var isImage = (side === 'back' ? d.docBackImage : d.docFrontImage) === '1';

    var img = document.getElementById('workforce_crm_detail_img_docview');
    var empty = document.getElementById('workforce_crm_detail_p_docview_empty');
    if (img) {
      if (url && isImage) { img.src = url; img.hidden = false; }
      else { img.removeAttribute('src'); img.hidden = true; }
    }
    if (empty) {
      empty.hidden = !!(url && isImage);
      empty.textContent = url
        ? 'This side is not an image and cannot be shown here.'
        : 'No scan has been uploaded for this document.';
    }
    var tools = document.getElementById('workforce_crm_detail_div_docview_tools');
    if (tools) tools.hidden = !(url && isImage);
    document.querySelectorAll('.crmdoc__side').forEach(function (b) {
      b.classList.toggle('is-active', b.getAttribute('data-doc-side') === side);
    });
    docRefreshDirty();
  }

  // ── In-popup image edit (Cropper.js) + number/expiry fields ─────────────
  // Nothing is written until Submit, and Submit shows only once the scan has
  // really been cropped/rotated or a field differs from what is on file.
  var docCropper = null;
  var docRotation = 0;      // quarter turns applied to the scan on show, in degrees
  var docOriginal = null;   // the untouched scan as loaded; every rotation redraws from it
  var docObjectUrl = null;  // the rotated copy currently under the cropper

  function docEl(id) { return document.getElementById(id); }

  function docStopCropper() {
    var img = docEl('workforce_crm_detail_img_docview');
    if (img) img.onload = null;   // a cropper still loading must not start on the next side
    if (docCropper) { docCropper.destroy(); docCropper = null; }
    if (docObjectUrl) { URL.revokeObjectURL(docObjectUrl); docObjectUrl = null; }
    docRotation = 0;
    docOriginal = null;
    var reset = document.querySelector('[data-doc-tool="reset"]');
    if (reset) reset.hidden = true;
    var stage = document.querySelector('.crmdoc__stage');
    if (stage) stage.classList.remove('is-editing');
  }

  // (Re)build the cropper on the scan turned by docRotation. Rotating the pixels
  // rather than using Cropper's own rotate keeps the photo a plain upright image,
  // so the cropper always fits it inside the frame.
  function docBuildCropper() {
    var img = docEl('workforce_crm_detail_img_docview');
    if (!img || !docOriginal) return;
    if (docCropper) { docCropper.destroy(); docCropper = null; }

    var mount = function (src) {
      var stage = img.closest('.crmdoc__stage');
      if (stage) stage.classList.add('is-editing');
      img.onload = function () {
        img.onload = null;
        docCropper = new Cropper(img, {
          viewMode: 1, autoCropArea: 1, background: false, responsive: true,
          ready: function () { docRefreshDirty(); },
          crop: function () { docRefreshDirty(); },
        });
        var reset = document.querySelector('[data-doc-tool="reset"]');
        if (reset) reset.hidden = false;
      };
      img.src = src;
    };

    if (!docRotation) { mount(docOriginal.src); return; }
    var quarter = docRotation % 180 !== 0;
    var w = docOriginal.naturalWidth, h = docOriginal.naturalHeight;
    var canvas = document.createElement('canvas');
    canvas.width = quarter ? h : w;
    canvas.height = quarter ? w : h;
    var ctx = canvas.getContext('2d');
    ctx.translate(canvas.width / 2, canvas.height / 2);
    ctx.rotate(docRotation * Math.PI / 180);
    ctx.drawImage(docOriginal, -w / 2, -h / 2);
    canvas.toBlob(function (blob) {
      if (!blob) return;
      if (docObjectUrl) URL.revokeObjectURL(docObjectUrl);
      docObjectUrl = URL.createObjectURL(blob);
      mount(docObjectUrl);
    }, 'image/jpeg', 0.97);
  }

  function docStartCropper() {
    if (docCropper || docOriginal) { docBuildCropper(); return; }
    if (typeof Cropper === 'undefined') {
      window.alert('The crop tool could not load. Check your connection and reload the page.');
      return;
    }
    var img = docEl('workforce_crm_detail_img_docview');
    if (!img || img.hidden || !img.getAttribute('src')) return;
    // Load the file fresh so a re-crop reads what was just saved, not the cached copy.
    var original = new Image();
    original.onload = function () { docOriginal = original; docBuildCropper(); };
    original.src = img.getAttribute('src').split('?')[0] + '?t=' + Date.now();
  }

  function docRotate(deg) {
    docRotation = (docRotation + deg + 360) % 360;
    docStartCropper();
  }

  // An untouched upright full-frame box is not an edit: never re-encode a
  // document of record into a lossier copy of itself (same rule as the driver page).
  function docImageDirty() {
    if (!docCropper || !docCropper.ready) return false;
    if (docRotation) return true;
    var d = docCropper.getData(true);
    var img = docCropper.getImageData();
    var slack = 2;
    return !(Math.abs(d.x) <= slack && Math.abs(d.y) <= slack
      && Math.abs(d.width - img.naturalWidth) <= slack
      && Math.abs(d.height - img.naturalHeight) <= slack);
  }

  function docFieldsDirty() {
    if (!docShown || docShown.docType === 'Selfie') return false;   // selfie name is display-only
    var no = docEl('workforce_crm_detail_input_docview_no');
    var exp = docEl('workforce_crm_detail_input_docview_expiry');
    return (no && no.value.trim() !== (docShown.docNo || ''))
      || (exp && exp.value !== (docShown.docExpiry || ''));
  }

  function docRefreshDirty() {
    var submit = docEl('workforce_crm_detail_btn_docsubmit');
    if (submit) submit.hidden = !(docFieldsDirty() || docImageDirty());
  }

  function docShowError(msg) {
    var err = docEl('workforce_crm_detail_p_docview_err');
    if (!err) return;
    err.textContent = msg || '';
    err.hidden = !msg;
  }

  function docPostJson(url, fd) {
    fd.append('csrfmiddlewaretoken', cfg().csrfToken || '');
    return fetch(url, { method: 'POST', body: fd })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.success) throw new Error(data.error || 'Could not save this document.');
        return data;
      });
  }

  function docSubmit(btn) {
    if (!docShown) return;
    var base = (cfg().urlDocEditBase || '') + docShown.docId;
    var fieldsDirty = docFieldsDirty();
    var imageDirty = docImageDirty();
    var side = docSide;
    docShowError('');
    btn.disabled = true;

    var chain = Promise.resolve();
    if (fieldsDirty) {
      chain = chain.then(function () {
        // The edit endpoint rewrites every field it is sent, so type and
        // issuer go back exactly as they are on file.
        var fd = new FormData();
        fd.append('document_type', docShown.docType || '');
        fd.append('document_no', docEl('workforce_crm_detail_input_docview_no').value.trim());
        fd.append('document_issued_from', docShown.docIssued || '');
        fd.append('document_expiry_date', docEl('workforce_crm_detail_input_docview_expiry').value);
        return docPostJson(base + '/edit/', fd);
      });
    }
    if (imageDirty) {
      var canvas = docCropper.getCroppedCanvas({ maxWidth: 3000, maxHeight: 3000, imageSmoothingQuality: 'high' });
      chain = chain.then(function () {
        return new Promise(function (resolve, reject) {
          if (!canvas) { reject(new Error('Could not read the crop area — try again.')); return; }
          canvas.toBlob(function (blob) {
            if (!blob) { reject(new Error('Could not build the edited image.')); return; }
            var fd = new FormData();
            fd.append('side', side);
            fd.append('image', blob, 'crop.jpg');
            docPostJson(base + '/crop/', fd).then(resolve, reject);
          }, 'image/jpeg', 0.92);
        });
      });
    }
    chain
      .then(function () { window.location.reload(); })
      .catch(function (err) {
        btn.disabled = false;
        docShowError(err && err.message ? err.message : 'Could not reach the server. Try again.');
      });
  }

  document.addEventListener('input', function (e) {
    if (e.target && (e.target.id === 'workforce_crm_detail_input_docview_no'
        || e.target.id === 'workforce_crm_detail_input_docview_expiry')) docRefreshDirty();
  });
  document.addEventListener('hidden.bs.modal', function (e) {
    if (e.target && e.target.id === 'workforce_crm_detail_modal_docview') docStopCropper();
  });

  function docOpenViewer(row) {
    docShown = Object.assign({}, row.dataset);
    var title = document.getElementById('workforce_crm_detail_h_docview_title');
    if (title) title.textContent = docShown.docType || 'Document';

    var facts = document.getElementById('workforce_crm_detail_dl_docview_facts');
    if (facts) {
      facts.textContent = '';
      docFact(facts, 'Issued from', docShown.docIssued);
      docFact(facts, 'Image check', docShown.docCheck);
      docFact(facts, 'Why', docShown.docCheckNote);
      docFact(facts, 'Number on image', docShown.docAiNo);
      docFact(facts, 'Expiry on image', docShown.docAiExpiry);
    }
    var sides = document.getElementById('workforce_crm_detail_div_docview_sides');
    if (sides) sides.hidden = !docShown.docBack;
    var verified = docShown.docVerified === '1';
    var vBtn = document.getElementById('workforce_crm_detail_btn_docverify');
    var uBtn = document.getElementById('workforce_crm_detail_btn_docunverify');
    if (vBtn) { vBtn.hidden = verified; vBtn.disabled = false; }
    if (uBtn) { uBtn.hidden = !verified; uBtn.disabled = false; }
    var noInput = docEl('workforce_crm_detail_input_docview_no');
    var expInput = docEl('workforce_crm_detail_input_docview_expiry');
    // A selfie has no number or expiry: show whose face it is (profile name), read-only.
    var isSelfie = docShown.docType === 'Selfie';
    var noLabel = docEl('workforce_crm_detail_label_docview_no');
    var expCol = docEl('workforce_crm_detail_div_docview_expiry');
    if (noLabel) noLabel.textContent = isSelfie ? 'Name' : 'Number';
    if (expCol) expCol.hidden = isSelfie;
    if (noInput) {
      noInput.value = isSelfie ? (docShown.docName || '') : (docShown.docNo || '');
      noInput.readOnly = isSelfie;
    }
    if (expInput) expInput.value = docShown.docExpiry || '';
    var submit = docEl('workforce_crm_detail_btn_docsubmit');
    if (submit) submit.disabled = false;
    docShowError('');

    docPaintSide(row.getAttribute('data-doc-start-side') || 'front');
    var modal = docModal('workforce_crm_detail_modal_docview');
    if (modal) modal.show();
  }

  document.addEventListener('click', function (e) {
    if (!e.target.closest) return;

    var row = e.target.closest('.crmdoc__row, [data-doc-open]');
    if (row) { docOpenViewer(row); return; }

    var side = e.target.closest('.crmdoc__side');
    if (side) {
      var to = side.getAttribute('data-doc-side');
      if (to !== docSide && docImageDirty()
          && !window.confirm('Discard the crop/rotate on this side?')) return;
      docPaintSide(to);
      return;
    }

    var tool = e.target.closest('[data-doc-tool]');
    if (tool) {
      var name = tool.getAttribute('data-doc-tool');
      if (name === 'reset') { docStopCropper(); docPaintSide(docSide); return; }
      if (name === 'rotate-left') docRotate(-90);
      else if (name === 'rotate-right') docRotate(90);
      else if (!docCropper) docStartCropper();
      return;
    }

    var submitBtn = e.target.closest('#workforce_crm_detail_btn_docsubmit');
    if (submitBtn) { docSubmit(submitBtn); return; }

    var verifyBtn = e.target.closest('#workforce_crm_detail_btn_docverify, #workforce_crm_detail_btn_docunverify');
    if (verifyBtn && docShown) {
      var undo = verifyBtn.id === 'workforce_crm_detail_btn_docunverify';
      if (!undo && !window.confirm('Confirm you checked the number and expiry against the image?')) return;
      verifyBtn.disabled = true;
      var vfd = new FormData();
      vfd.append('action', undo ? 'unverify' : 'verify');
      vfd.append('csrfmiddlewaretoken', cfg().csrfToken || '');
      fetch((cfg().urlDocEditBase || '') + docShown.docId + '/verify/', { method: 'POST', body: vfd })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.success) { window.location.reload(); return; }
          verifyBtn.disabled = false;
          window.alert(data.error || 'Could not update verification.');
        })
        .catch(function () {
          verifyBtn.disabled = false;
          window.alert('Could not reach the server. Try again.');
        });
      return;
    }
  });

})();
