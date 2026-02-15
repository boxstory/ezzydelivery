/**
 * Dashboard Tables - DataTables Custom Configurations
 * EzzyDelivery Qatar
 */

// Common DataTable configuration presets
const TABLE_PRESETS = {
  // Standard table with search, pagination
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

  // Table with export buttons
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

  // Compact table for mobile
  compact: {
    responsive: {
      details: {
        display: $.fn.dataTable.Responsive.display.modal({
          header: function(row) {
            const data = row.data();
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

  // Server-side processing for large datasets
  serverSide: {
    processing: true,
    serverSide: true,
    ajax: {
      url: '', // Set dynamically
      type: 'GET',
      data: function(d) {
        // Add custom filters
        d.status = $('#statusFilter').val();
        d.date_from = $('#dateFrom').val();
        d.date_to = $('#dateTo').val();
      }
    },
    pageLength: 25,
    responsive: true
  }
};

/**
 * Initialize Orders Table
 */
function initOrdersTable() {
  if ($('#ordersTable').length && !$.fn.DataTable.isDataTable('#ordersTable')) {
    $('#ordersTable').DataTable({
      ...TABLE_PRESETS.export,
      order: [[0, 'desc']], // Sort by order ID descending
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
        // Reinitialize tooltips after redraw
        $('[data-bs-toggle="tooltip"]').tooltip();
      }
    });
  }
}

/**
 * Initialize Drivers Table
 */
function initDriversTable() {
  if ($('#driversTable').length && !$.fn.DataTable.isDataTable('#driversTable')) {
    $('#driversTable').DataTable({
      ...TABLE_PRESETS.standard,
      order: [[1, 'asc']], // Sort by driver name
      columnDefs: [
        {
          targets: 0,
          render: function(data, type, row) {
            // Custom rendering for status badges
            const statusColors = {
              'Approved': 'success',
              'Pending': 'warning',
              'Suspended': 'danger'
            };
            return `<span class="badge bg-${statusColors[data] || 'secondary'}">${data}</span>`;
          }
        }
      ]
    });
  }
}

/**
 * Initialize Tasks Table
 */
function initTasksTable() {
  if ($('#tasksTable').length && !$.fn.DataTable.isDataTable('#tasksTable')) {
    $('#tasksTable').DataTable({
      ...TABLE_PRESETS.export,
      order: [[2, 'desc']], // Sort by created date
      columnDefs: [
        {
          targets: 'status-column',
          render: function(data, type, row) {
            const statusIcons = {
              'delivered': '<i class="fa-solid fa-check-circle text-success"></i>',
              'in_transit': '<i class="fa-solid fa-truck text-primary"></i>',
              'pending': '<i class="fa-solid fa-clock text-warning"></i>',
              'failed': '<i class="fa-solid fa-times-circle text-danger"></i>'
            };
            return `${statusIcons[data] || ''} ${data}`;
          }
        }
      ]
    });
  }
}

/**
 * Initialize COD Transactions Table
 */
function initCODTable() {
  if ($('#codTable').length && !$.fn.DataTable.isDataTable('#codTable')) {
    $('#codTable').DataTable({
      ...TABLE_PRESETS.export,
      order: [[0, 'desc']],
      footerCallback: function() {
        const api = this.api();

        // Calculate total COD amount
        const total = api
          .column(3, {page: 'current'})
          .data()
          .reduce((a, b) => parseFloat(a) + parseFloat(b), 0);

        // Update footer
        $(api.column(3).footer()).html(
          `<strong>Total: QAR ${total.toFixed(2)}</strong>`
        );
      }
    });
  }
}

/**
 * Add custom search to specific column
 */
function addColumnSearch(table, columnIndex, placeholder) {
  table.column(columnIndex).every(function() {
    const column = this;
    $('<input type="text" class="form-control form-control-sm" placeholder="' + placeholder + '" />')
      .appendTo($(column.footer()).empty())
      .on('keyup change clear', function() {
        if (column.search() !== this.value) {
          column.search(this.value).draw();
        }
      });
  });
}

/**
 * Export table data with custom formatting
 */
function exportTableData(tableId, format) {
  const table = $(`#${tableId}`).DataTable();

  if (format === 'excel') {
    table.button('.buttons-excel').trigger();
  } else if (format === 'pdf') {
    table.button('.buttons-pdf').trigger();
  } else if (format === 'print') {
    table.button('.buttons-print').trigger();
  }
}

/**
 * Refresh table data via AJAX
 */
function refreshTableData(tableId, url) {
  const table = $(`#${tableId}`).DataTable();

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

// Auto-initialize tables on DOM ready
document.addEventListener('DOMContentLoaded', function() {
  if (typeof $.fn.DataTable !== 'undefined') {
    initOrdersTable();
    initDriversTable();
    initTasksTable();
    initCODTable();
  }
});

// Reinitialize after HTMX swap
document.body.addEventListener('htmx:afterSwap', function(evt) {
  setTimeout(function() {
    initOrdersTable();
    initDriversTable();
    initTasksTable();
    initCODTable();
  }, 100);
});
