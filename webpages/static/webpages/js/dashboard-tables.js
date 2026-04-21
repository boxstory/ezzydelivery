/**
 * Dashboard Tables - DataTables Custom Configurations
 * EzzyDelivery Qatar
 */

var TABLE_PRESETS = {
  standard: {
    responsive: true,
    pageLength: 25,
    lengthMenu: [[10, 25, 50, 100], [10, 25, 50, 100]],
    dom: 'frtip',
    language: {
      search: "_INPUT_",
      searchPlaceholder: "Search...",
      lengthMenu: "Show _MENU_ entries"
    }
  },

  export: {
    responsive: true,
    pageLength: 25,
    dom: 'Bfrtip',
    buttons: [
      {
        extend: 'excel',
        text: '<i class="fa-solid fa-file-excel me-1"></i> Excel',
        className: 'btn btn-sm btn-success',
        exportOptions: {
          columns: ':visible:not(.no-export)'
        }
      },
      {
        extend: 'pdf',
        text: '<i class="fa-solid fa-file-pdf me-1"></i> PDF',
        className: 'btn btn-sm btn-danger',
        exportOptions: {
          columns: ':visible:not(.no-export)'
        }
      },
      {
        extend: 'print',
        text: '<i class="fa-solid fa-print me-1"></i> Print',
        className: 'btn btn-sm btn-secondary',
        exportOptions: {
          columns: ':visible:not(.no-export)'
        }
      }
    ]
  },

  compact: {
    responsive: {
      details: {
        display: $.fn.dataTable.Responsive.display.modal({
          header: function(row) {
            var data = row.data();
            return 'Details: ' + data[0];
          }
        }),
        renderer: $.fn.dataTable.Responsive.renderer.tableAll()
      }
    },
    pageLength: 10,
    dom: 'ftp',
    language: {
      paginate: {
        previous: '‹',
        next: '›'
      }
    }
  },

  serverSide: {
    processing: true,
    serverSide: true,
    ajax: {
      url: '',
      type: 'GET',
      data: function(d) {
        d.status = $('#statusFilter').val();
        d.date_from = $('#dateFrom').val();
        d.date_to = $('#dateTo').val();
      }
    },
    pageLength: 25,
    responsive: true
  }
};

function initOrdersTable() {
  if ($('#ordersTable').length && !$.fn.DataTable.isDataTable('#ordersTable')) {
    var config = jQuery.extend({}, TABLE_PRESETS.export, {
      order: [[0, 'desc']],
      columnDefs: [
        {
          targets: 'no-sort',
          orderable: false
        },
        {
          targets: 'no-export',
          exportOptions: false
        }
      ],
      drawCallback: function() {
        $('[data-bs-toggle="tooltip"]').tooltip();
      }
    });
    $('#ordersTable').DataTable(config);
  }
}

function initDriversTable() {
  if ($('#driversTable').length && !$.fn.DataTable.isDataTable('#driversTable')) {
    var config = jQuery.extend({}, TABLE_PRESETS.standard, {
      order: [[1, 'asc']],
      columnDefs: [
        {
          targets: 0,
          render: function(data, type, row) {
            var statusColors = {
              'Approved': 'success',
              'Pending': 'warning',
              'Suspended': 'danger'
            };
            var color = statusColors[data] || 'secondary';
            return '<span class="badge bg-' + color + '">' + data + '</span>';
          }
        }
      ]
    });
    $('#driversTable').DataTable(config);
  }
}

function initTasksTable() {
  if ($('#tasksTable').length && !$.fn.DataTable.isDataTable('#tasksTable')) {
    var config = jQuery.extend({}, TABLE_PRESETS.export, {
      order: [[2, 'desc']],
      columnDefs: [
        {
          targets: 'status-column',
          render: function(data, type, row) {
            var statusIcons = {
              'delivered': '<i class="fa-solid fa-check-circle text-success"></i>',
              'in_transit': '<i class="fa-solid fa-truck text-primary"></i>',
              'pending': '<i class="fa-solid fa-clock text-warning"></i>',
              'failed': '<i class="fa-solid fa-times-circle text-danger"></i>'
            };
            var icon = statusIcons[data] || '';
            return icon + ' ' + data;
          }
        }
      ]
    });
    $('#tasksTable').DataTable(config);
  }
}

function initCODTable() {
  if ($('#codTable').length && !$.fn.DataTable.isDataTable('#codTable')) {
    var config = jQuery.extend({}, TABLE_PRESETS.export, {
      order: [[0, 'desc']],
      footerCallback: function() {
        var api = this.api();
        var total = 0;
        var data = api.column(3, {page: 'current'}).data();
        for (var i = 0; i < data.length; i++) {
          total += parseFloat(data[i]) || 0;
        }
        $(api.column(3).footer()).html(
          '<strong>Total: QAR ' + total.toFixed(2) + '</strong>'
        );
      }
    });
    $('#codTable').DataTable(config);
  }
}

function addColumnSearch(table, columnIndex, placeholder) {
  table.column(columnIndex).every(function() {
    var column = this;
    $('<input type="text" class="form-control form-control-sm" placeholder="' + placeholder + '" />')
      .appendTo($(column.footer()).empty())
      .on('keyup change clear', function() {
        if (column.search() !== this.value) {
          column.search(this.value).draw();
        }
      });
  });
}

function exportTableData(tableId, format) {
  var table = $('#' + tableId).DataTable();

  if (format === 'excel') {
    table.button('.buttons-excel').trigger();
  } else if (format === 'pdf') {
    table.button('.buttons-pdf').trigger();
  } else if (format === 'print') {
    table.button('.buttons-print').trigger();
  }
}

function refreshTableData(tableId, url) {
  var table = $('#' + tableId).DataTable();

  $.ajax({
    url: url,
    method: 'GET',
    success: function(data) {
      table.clear();
      table.rows.add(data);
      table.draw();
      showSuccess('Table refreshed');
    },
    error: function() {
      showError('Failed to refresh table');
    }
  });
}

document.addEventListener('DOMContentLoaded', function() {
  if (typeof $.fn.DataTable !== 'undefined') {
    initOrdersTable();
    initDriversTable();
    initTasksTable();
    initCODTable();
  }
});

document.body.addEventListener('htmx:afterSwap', function(evt) {
  setTimeout(function() {
    initOrdersTable();
    initDriversTable();
    initTasksTable();
    initCODTable();
  }, 100);
});
