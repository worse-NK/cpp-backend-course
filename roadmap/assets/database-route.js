(function () {
  'use strict';
  var sqlIds = ['sql-language','sql-first-query','sql-create-basics','tables','sql-select-basics','sql-filter-basics','sql-null-basics','sql-order-basics','sql-write-basics','queries','sql-join-basics','worked-example','sql-boundaries','sql-trainer','sql-aggregate-basics','aggregation','join-shapes'];
  function redirect() {
    if (!location.pathname.endsWith('/cpp_station9_databases.html')) return;
    var params = new URLSearchParams(location.hash.slice(1));
    if (sqlIds.indexOf(params.get('section')) >= 0 || (params.get('view') === 'checkpoint' && ['tables','queries','aggregation'].indexOf(params.get('module')) >= 0)) {
      location.replace('cpp_station9_sql.html' + location.hash);
    }
  }
  // Only lesson markers migrate: new exams have a different scope.
  if (location.pathname.endsWith('/cpp_station9_sql.html')) {
    try {
      var key = 'cpp_station9_sql_progress_v1';
      var next = JSON.parse(localStorage.getItem(key)) || {};
      if (!next.migratedFromDatabases) {
        var old = JSON.parse(localStorage.getItem('cpp_station9_progress_v1')) || {};
        sqlIds.forEach(function (id) { if (old['sec:' + id] && next['sec:' + id] === undefined) next['sec:' + id] = true; });
        next.migratedFromDatabases = true;
        localStorage.setItem(key, JSON.stringify(next));
      }
    } catch (_) { /* Reading works without storage. */ }
  }
  window.addEventListener('hashchange', redirect);
  redirect();
}());
