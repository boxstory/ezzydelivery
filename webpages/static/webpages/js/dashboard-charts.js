/**
 * Dashboard Charts - ApexCharts Wrapper
 * EzzyDelivery Qatar
 */

// Global chart configuration
var CHART_DEFAULTS = {
  fontFamily: 'Inter, Poppins, sans-serif',
  colors: ['#f7c000', '#001f3f', '#10B981', '#EF4444', '#3B82F6', '#F59E0B'],
  theme: {
    mode: 'light',
    palette: 'palette1'
  },
  chart: {
    toolbar: {
      show: true,
      tools: {
        download: true,
        selection: false,
        zoom: false,
        zoomin: false,
        zoomout: false,
        pan: false,
        reset: false
      }
    },
    fontFamily: 'Inter, Poppins, sans-serif'
  },
  dataLabels: {
    enabled: false
  },
  stroke: {
    curve: 'smooth',
    width: 3
  },
  grid: {
    borderColor: '#e0e0e0',
    strokeDashArray: 4
  },
  xaxis: {
    labels: {
      style: {
        colors: '#6c757d',
        fontSize: '12px'
      }
    }
  },
  yaxis: {
    labels: {
      style: {
        colors: '#6c757d',
        fontSize: '12px'
      }
    }
  },
  legend: {
    position: 'top',
    horizontalAlign: 'left',
    fontSize: '13px',
    fontWeight: 500,
    labels: {
      colors: '#333'
    }
  },
  tooltip: {
    theme: 'light',
    style: {
      fontSize: '13px'
    }
  }
};

/**
 * Create Line Chart
 */
function createLineChart(elementId, data, options) {
  options = options || {};
  var chartOptions = Object.assign({}, CHART_DEFAULTS, {
    series: data.series,
    chart: Object.assign({}, CHART_DEFAULTS.chart, {
      type: 'line',
      height: options.height || 350,
      zoom: { enabled: false }
    }),
    xaxis: Object.assign({}, CHART_DEFAULTS.xaxis, {
      categories: data.categories
    })
  }, options);

  var chart = new ApexCharts(document.querySelector('#' + elementId), chartOptions);
  chart.render();
  return chart;
}

/**
 * Create Area Chart
 */
function createAreaChart(elementId, data, options) {
  options = options || {};
  var chartOptions = Object.assign({}, CHART_DEFAULTS, {
    series: data.series,
    chart: Object.assign({}, CHART_DEFAULTS.chart, {
      type: 'area',
      height: options.height || 350
    }),
    xaxis: Object.assign({}, CHART_DEFAULTS.xaxis, {
      categories: data.categories
    }),
    fill: {
      type: 'gradient',
      gradient: {
        shadeIntensity: 1,
        opacityFrom: 0.7,
        opacityTo: 0.3,
        stops: [0, 90, 100]
      }
    }
  }, options);

  var chart = new ApexCharts(document.querySelector('#' + elementId), chartOptions);
  chart.render();
  return chart;
}

/**
 * Create Bar Chart
 */
function createBarChart(elementId, data, options) {
  options = options || {};
  var chartOptions = Object.assign({}, CHART_DEFAULTS, {
    series: data.series,
    chart: Object.assign({}, CHART_DEFAULTS.chart, {
      type: 'bar',
      height: options.height || 350
    }),
    plotOptions: {
      bar: {
        horizontal: options.horizontal || false,
        borderRadius: 8,
        dataLabels: {
          position: 'top'
        }
      }
    },
    xaxis: Object.assign({}, CHART_DEFAULTS.xaxis, {
      categories: data.categories
    })
  }, options);

  var chart = new ApexCharts(document.querySelector('#' + elementId), chartOptions);
  chart.render();
  return chart;
}

/**
 * Create Donut Chart
 */
function createDonutChart(elementId, data, options) {
  options = options || {};
  var chartOptions = Object.assign({}, CHART_DEFAULTS, {
    series: data.series,
    chart: Object.assign({}, CHART_DEFAULTS.chart, {
      type: 'donut',
      height: options.height || 350
    }),
    labels: data.labels,
    plotOptions: {
      pie: {
        donut: {
          size: '70%',
          labels: {
            show: true,
            total: {
              show: true,
              label: options.totalLabel || 'Total',
              fontSize: '16px',
              fontWeight: 600
            }
          }
        }
      }
    },
    dataLabels: {
      enabled: true,
      formatter: function(val) {
        return val.toFixed(1) + '%';
      }
    },
    legend: {
      position: 'bottom'
    }
  }, options);

  var chart = new ApexCharts(document.querySelector('#' + elementId), chartOptions);
  chart.render();
  return chart;
}

/**
 * Create Radial Bar Chart (Progress/Gauge)
 */
function createRadialChart(elementId, data, options) {
  options = options || {};
  var chartOptions = Object.assign({}, CHART_DEFAULTS, {
    series: data.series,
    chart: Object.assign({}, CHART_DEFAULTS.chart, {
      type: 'radialBar',
      height: options.height || 300
    }),
    plotOptions: {
      radialBar: {
        hollow: {
          size: '70%'
        },
        dataLabels: {
          name: {
            fontSize: '16px'
          },
          value: {
            fontSize: '24px',
            fontWeight: 700,
            formatter: function(val) {
              return val + '%';
            }
          }
        }
      }
    },
    labels: data.labels || ['Progress']
  }, options);

  var chart = new ApexCharts(document.querySelector('#' + elementId), chartOptions);
  chart.render();
  return chart;
}

/**
 * Example Usage - Revenue Trend Chart
 */
function initRevenueTrendChart() {
    var revenueData = {
    series: [{
      name: 'Revenue (QAR)',
      data: [12000, 19000, 15000, 25000, 22000, 30000, 28000]
    }],
    categories: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
  };

  if (document.querySelector('#revenueChart')) {
    createAreaChart('revenueChart', revenueData, {
      colors: ['#f7c000'],
      title: {
        text: 'Revenue Trend',
        align: 'left'
      }
    });
  }
}

/**
 * Example Usage - Order Status Breakdown
 */
function initOrderStatusChart() {
    var statusData = {
    series: [35, 25, 20, 15, 5],
    labels: ['Delivered', 'In Transit', 'Pending', 'Assigned', 'Failed']
  };

  if (document.querySelector('#orderStatusChart')) {
    createDonutChart('orderStatusChart', statusData, {
      colors: ['#10B981', '#3B82F6', '#F59E0B', '#f7c000', '#EF4444'],
      totalLabel: 'Total Orders'
    });
  }
}

/**
 * Example Usage - Driver Performance
 */
function initDriverPerformanceChart() {
    var performanceData = {
    series: [85],
    labels: ['Completion Rate']
  };

  if (document.querySelector('#driverPerformanceChart')) {
    createRadialChart('driverPerformanceChart', performanceData, {
      colors: ['#10B981']
    });
  }
}

// Initialize all charts on page load
document.addEventListener('DOMContentLoaded', function() {
  if (typeof ApexCharts !== 'undefined') {
    initRevenueTrendChart();
    initOrderStatusChart();
    initDriverPerformanceChart();
  }
});
