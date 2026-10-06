/* Purpose: The driver-document popup — scan viewer with crop/rotate, number + expiry fields ("Use values from image" fills them), Submit / Submit & verify on change, staff Verify / Undo, Previous / Next through the page's documents, mouse-wheel zoom + drag pan on the scan.
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

  // ── Wheel zoom on the scan (view mode only) ─────────────────────────────
  // translate + scale from a top-left origin; the wheel picks the translate that
  // keeps the point under the pointer still. Pan is clamped to the frame: a scan
  // larger than the frame always fills it, a smaller one stays inside it.
  // Crop mode has Cropper's own wheel zoom.
  var DOC_ZOOM_MAX = 8;
  var docZoom = { s: 1, x: 0, y: 0 };
  var docPan = null;   // the drag in progress: pointer id, start point, start offset

  // One axis: `start` is where the unzoomed scan sits in the frame, `frame` the
  // frame's length, `size` the zoomed scan's. Flush-start and flush-end bound the offset.
  function docClampPan(t, size, start, frame) {
    var lo = -start, hi = frame - start - size;
    return size >= frame ? Math.min(lo, Math.max(hi, t)) : Math.min(hi, Math.max(lo, t));
  }

  function docZoomApply() {
    var img = docEl('workforce_crm_detail_img_docview');
    if (!img) return;
    var z = docZoom;
    if (z.s <= 1) { z.s = 1; z.x = 0; z.y = 0; }
    var stage = img.closest('.crmdoc__stage');
    if (stage && z.s > 1) {
      // The stage is the scan's offsetParent, so offsetLeft/Top are frame coordinates.
      z.x = docClampPan(z.x, img.offsetWidth * z.s, img.offsetLeft, stage.clientWidth);
      z.y = docClampPan(z.y, img.offsetHeight * z.s, img.offsetTop, stage.clientHeight);
    }
    img.style.transform = z.s === 1 ? '' : 'translate(' + z.x + 'px, ' + z.y + 'px) scale(' + z.s + ')';
    if (stage) stage.classList.toggle('is-zoomed', z.s > 1);
    var chip = docEl('workforce_crm_detail_btn_docview_zoom');
    if (chip) {
      chip.hidden = z.s === 1;
      chip.textContent = Math.round(z.s * 100) + '%';
    }
  }

  function docZoomReset() {
    docZoom = { s: 1, x: 0, y: 0 };
    docPan = null;
    var stage = document.querySelector('.crmdoc__stage');
    if (stage) stage.classList.remove('is-panning');
    docZoomApply();
  }

  function docZoomable(stage) {
    var img = docEl('workforce_crm_detail_img_docview');
    return img && !img.hidden && img.getAttribute('src') && !stage.classList.contains('is-editing');
  }

  function docZoomWheel(e) {
    var stage = e.currentTarget;
    if (!docZoomable(stage)) return;
    // Lines / pages (Firefox) to pixels, so every wheel steps about the same.
    var dy = e.deltaY * (e.deltaMode === 1 ? 33 : e.deltaMode === 2 ? 400 : 1);
    var next = Math.min(DOC_ZOOM_MAX, Math.max(1, docZoom.s * Math.exp(-dy * 0.002)));
    if (next === docZoom.s) return;   // at a limit: let the wheel scroll the dialog
    e.preventDefault();
    var img = docEl('workforce_crm_detail_img_docview');
    var rect = img.getBoundingClientRect();
    var mx = e.clientX - (rect.left - docZoom.x);   // pointer, in the unzoomed box
    var my = e.clientY - (rect.top - docZoom.y);
    docZoom.x = mx - next * (mx - docZoom.x) / docZoom.s;
    docZoom.y = my - next * (my - docZoom.y) / docZoom.s;
    docZoom.s = next;
    docZoomApply();
  }

  // Bound to the stage itself, not the document: a non-passive wheel listener on
  // the document would slow scrolling on the whole page. Re-bound after an HTMX
  // swap because the flag lives on the (new) element.
  function docBindZoom() {
    var stage = document.querySelector('.crmdoc__stage');
    if (!stage || stage.dataset.zoomBound) return;
    stage.dataset.zoomBound = '1';
    stage.addEventListener('wheel', docZoomWheel, { passive: false });
    stage.addEventListener('pointerdown', function (e) {
      if (docZoom.s <= 1 || e.button !== 0 || !docZoomable(stage)
          || e.target.closest('.crmdoc__zoom')) return;
      e.preventDefault();
      docPan = { id: e.pointerId, sx: e.clientX, sy: e.clientY, x: docZoom.x, y: docZoom.y };
      stage.setPointerCapture(e.pointerId);
      stage.classList.add('is-panning');
    });
    stage.addEventListener('pointermove', function (e) {
      if (!docPan || e.pointerId !== docPan.id) return;
      docZoom.x = docPan.x + e.clientX - docPan.sx;
      docZoom.y = docPan.y + e.clientY - docPan.sy;
      docZoomApply();
    });
    var endPan = function () { docPan = null; stage.classList.remove('is-panning'); };
    stage.addEventListener('pointerup', endPan);
    stage.addEventListener('pointercancel', endPan);
    stage.addEventListener('dblclick', function (e) {
      if (docZoomable(stage) && !e.target.closest('.crmdoc__zoom')) docZoomReset();
    });
  }

  function docStopCropper() {
    docZoomReset();
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
      docZoomReset();   // the cropper works on the whole scan, not the zoomed view
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

  // "Use values from image" shows only while the image check read something the
  // fields do not already hold — a click copies it in, and Submit takes it from there.
  function docAiDiffers() {
    if (!docShown || docShown.docType === 'Selfie') return false;
    var no = docEl('workforce_crm_detail_input_docview_no');
    var exp = docEl('workforce_crm_detail_input_docview_expiry');
    var aiNo = docShown.docAiNo || '', aiExp = docShown.docAiExpiryIso || '';
    return !!((aiNo && no && no.value.trim() !== aiNo) || (aiExp && exp && exp.value !== aiExp));
  }

  function docUseAiValues() {
    if (!docShown) return;
    var no = docEl('workforce_crm_detail_input_docview_no');
    var exp = docEl('workforce_crm_detail_input_docview_expiry');
    if (no && docShown.docAiNo) no.value = docShown.docAiNo;
    if (exp && docShown.docAiExpiryIso) exp.value = docShown.docAiExpiryIso;
    docRefreshDirty();
  }

  function docRefreshDirty() {
    var dirty = docFieldsDirty() || docImageDirty();
    var submit = docEl('workforce_crm_detail_btn_docsubmit');
    if (submit) submit.hidden = !dirty;
    var submitVerify = docEl('workforce_crm_detail_btn_docsubmitverify');
    if (submitVerify) submitVerify.hidden = !dirty;
    // While a field is edited, Submit & verify stands in for Mark verified, which
    // would verify the values still on file rather than the ones typed.
    var verify = docEl('workforce_crm_detail_btn_docverify');
    if (verify && docShown) verify.hidden = docShown.docVerified === '1' || dirty;
    var useAi = docEl('workforce_crm_detail_btn_docuseai');
    if (useAi) useAi.hidden = !docAiDiffers();
  }

  function docShowError(msg) {
    var err = docEl('workforce_crm_detail_p_docview_err');
    if (!err) return;
    err.textContent = msg || '';
    err.hidden = !msg;
  }

  // X-Requested-With makes a department refusal come back as JSON with its reason;
  // without it the middleware redirects and r.json() chokes on the dashboard HTML.
  function docFetchJson(url, fd) {
    fd.append('csrfmiddlewaretoken', cfg().csrfToken || '');
    return fetch(url, { method: 'POST', body: fd, headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) {
        return r.json().catch(function () {
          throw new Error('The server did not answer properly (HTTP ' + r.status + '). Reload the page and try again.');
        });
      });
  }

  function docPostJson(url, fd) {
    return docFetchJson(url, fd)
      .then(function (data) {
        if (!data.success) throw new Error(data.error || 'Could not save this document.');
        return data;
      });
  }

  // `verify` (Submit & verify) marks the document verified once the edits are saved,
  // so the verification is against the values just written, never the old ones.
  function docSubmit(verify) {
    if (!docShown) return;
    if (verify && !window.confirm('Confirm you checked the number and expiry against the image?')) return;
    var base = (cfg().urlDocEditBase || '') + docShown.docId;
    var fieldsDirty = docFieldsDirty();
    var imageDirty = docImageDirty();
    var side = docSide;
    var btns = [docEl('workforce_crm_detail_btn_docsubmit'), docEl('workforce_crm_detail_btn_docsubmitverify')];
    var setBusy = function (busy) { btns.forEach(function (b) { if (b) b.disabled = busy; }); };
    docShowError('');
    setBusy(true);

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
    if (verify) {
      chain = chain.then(function () {
        var vfd = new FormData();
        vfd.append('action', 'verify');
        return docPostJson(base + '/verify/', vfd);
      });
    }
    chain
      .then(function () { window.location.reload(); })
      .catch(function (err) {
        setBusy(false);
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

  // The documents Previous / Next step through, in page order — one opener per
  // document, since the driver record has several (front thumb, back thumb, View).
  function docSequence() {
    var seen = {};
    var list = [];
    document.querySelectorAll('.crmdoc__row, [data-doc-open]').forEach(function (el) {
      var id = el.getAttribute('data-doc-id');
      if (!id || seen[id]) return;
      seen[id] = true;
      list.push(el);
    });
    return list;
  }

  function docIndexIn(seq) {
    for (var i = 0; i < seq.length; i++) {
      if (seq[i].getAttribute('data-doc-id') === docShown.docId) return i;
    }
    return -1;
  }

  function docPaintNav() {
    var nav = docEl('workforce_crm_detail_div_docview_nav');
    if (!nav || !docShown) return;
    var seq = docSequence();
    var i = docIndexIn(seq);
    nav.hidden = seq.length < 2 || i < 0;
    if (nav.hidden) return;
    var pos = docEl('workforce_crm_detail_span_docview_pos');
    if (pos) pos.textContent = (i + 1) + ' of ' + seq.length;
    var prev = docEl('workforce_crm_detail_btn_docprev');
    var next = docEl('workforce_crm_detail_btn_docnext');
    if (prev) prev.disabled = i === 0;
    if (next) next.disabled = i === seq.length - 1;
  }

  function docStep(delta) {
    if (!docShown) return;
    if ((docFieldsDirty() || docImageDirty())
        && !window.confirm('Discard your unsaved changes to this document?')) return;
    var seq = docSequence();
    var to = seq[docIndexIn(seq) + delta];
    if (to) docOpenViewer(to);
  }

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
    ['workforce_crm_detail_btn_docsubmit', 'workforce_crm_detail_btn_docsubmitverify'].forEach(function (id) {
      var b = docEl(id);
      if (b) b.disabled = false;
    });
    docShowError('');
    docPaintNav();
    docBindZoom();

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

    if (e.target.closest('#workforce_crm_detail_btn_docview_zoom')) { docZoomReset(); return; }

    var stepBtn = e.target.closest('#workforce_crm_detail_btn_docprev, #workforce_crm_detail_btn_docnext');
    if (stepBtn) { docStep(stepBtn.id === 'workforce_crm_detail_btn_docnext' ? 1 : -1); return; }

    if (e.target.closest('#workforce_crm_detail_btn_docuseai')) { docUseAiValues(); return; }
    var submitBtn = e.target.closest('#workforce_crm_detail_btn_docsubmit, #workforce_crm_detail_btn_docsubmitverify');
    if (submitBtn) { docSubmit(submitBtn.id === 'workforce_crm_detail_btn_docsubmitverify'); return; }

    var verifyBtn = e.target.closest('#workforce_crm_detail_btn_docverify, #workforce_crm_detail_btn_docunverify');
    if (verifyBtn && docShown) {
      var undo = verifyBtn.id === 'workforce_crm_detail_btn_docunverify';
      if (!undo && !window.confirm('Confirm you checked the number and expiry against the image?')) return;
      verifyBtn.disabled = true;
      var vfd = new FormData();
      vfd.append('action', undo ? 'unverify' : 'verify');
      docFetchJson((cfg().urlDocEditBase || '') + docShown.docId + '/verify/', vfd)
        .then(function (data) {
          if (data.success) { window.location.reload(); return; }
          verifyBtn.disabled = false;
          window.alert(data.error || 'Could not update verification.');
        })
        .catch(function (err) {
          verifyBtn.disabled = false;
          window.alert(err && err.message ? err.message : 'Could not reach the server. Try again.');
        });
      return;
    }
  });

})();
