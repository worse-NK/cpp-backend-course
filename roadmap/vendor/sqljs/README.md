# sql.js 1.13.0

Upstream: https://github.com/sql-js/sql.js/tree/v1.13.0
Package: https://registry.npmjs.org/sql.js/-/sql.js-1.13.0.tgz

`sql-asm.js` is the unmodified upstream distribution, MIT license in `LICENSE`.
SHA-256: `c83beac167ae9c1af075449555b1db68b24b5280d0fc65c1f7ac4d1cd103459d`.
SQLite itself is public domain. The asm.js build requires no extra WASM fetch,
so the course can load the engine from a local file as well as HTTP.

`tools/build_sql_lab.py` embeds the engine and our worker code in a local script.
Queries run in disposable Blob workers, not on the page's main thread.
No SQL engine is downloaded at runtime; no user query is sent to a server.
This is SQLite, not an emulation of PostgreSQL transaction semantics.
