/* Local, declarative syntax highlighting. It never executes course examples. */
(function () {
  "use strict";
  var cache = new Map(), cacheLibrary = null;
  var outputCaption = /^(?:точный вывод|ожидаемый вывод|вывод программы|пример вывода|результат выполнения|ожидаемый результат|stdout|stderr|диагностика|сообщени[ея] (?:компилятора|линкера))/i;

  function languageFor(source, caption, stationId) {
    var text = String(source == null ? "" : source).trim();
    var label = String(caption || "").trim();
    if (!text || outputCaption.test(label)) return "plaintext";
    // Use explicit caption/source signatures, never probabilistic detection.
    // Unrecognised logs, addresses, diagrams and protocol payloads stay literal.
    if (/^(?:вывод|лог|трассировка|сообщение об ошибке)(?=[:\s]|$)/i.test(label) || /^(?:Traceback \(|ERROR:|error:|fatal error:|==\d+==)/m.test(text)) return "plaintext";
    // Recognise the outer source before inspecting embedded SQL/commands in a
    // raw string or a configuration value. They do not change its language.
    var leading = text.replace(/^(?:\s*(?:\/\/[^\n]*|\/\*[\s\S]*?\*\/)\s*)+/, "");
    if (/^(?:#\s*(?:include|pragma)\b|(?:class|struct|namespace|template)\b|(?:int|void|bool|double|float|size_t)\s+\w+\s*\(|std::)/.test(leading)) return "cpp";
    if (/^(?:def\s+\w+\s*\(|from\s+[\w.]+\s+import\s|import\s+[\w.]+|if\s+__name__\s*==)/.test(leading)) return "python";
    if (/^(?:apiVersion|kind|services|version|scrape_configs|receivers|exporters|processors|service|groups|name|on|jobs):/.test(leading)) return "yaml";
    if (/^(?:\$ |#!\s*\/.*(?:bash|sh)|(?:sudo|curl|wget|docker(?:-compose)?|kubectl|kind|redis-cli|psql|g\+\+|clang\+\+|cmake\s+-|make\s|ctest|git\s|ssh\s|ip\s|ss\s|tcpdump|tshark|nft\s|openssl\s|systemctl|journalctl|python3?\s|bash\s|export\s|cd\s|printf\s|echo\s|nc\s|dig\s|ping\s|ls\s|cat\s|strace\s|perf\s|valgrind\s|ulimit\s|sysctl\s|readelf\s|objdump\s|nm\s|ldd\s|grep\s|awk\s|sed\s|rm\s|mkdir\s|kill\s))/m.test(text) || /команды для|запуск вне учебника|команды в терминале/i.test(label)) return "bash";
    if (/^(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+\S+\s+HTTP\/|^HTTP\/\d/m.test(text)) return "http";
    if (/^(?:Host|Content-Type|Content-Length|Authorization|Accept|Connection|Cache-Control|Set-Cookie|Cookie|Location|X-Request-ID):/im.test(text)) return "http";
    if (/^(?:cmake_minimum_required|project|add_executable|add_library|find_package|target_\w+|set|include)\s*\(/m.test(text)) return "cmake";
    if (/^(?:FROM\s+\S+|WORKDIR\s+\S+|ENTRYPOINT\s+\[|CMD\s+\[)/m.test(text)) return "dockerfile";
    if (/^(?:events|http|upstream\s+\S+|server|location\s+\S+)\s*\{/m.test(text) && !/#include|std::|class\s/.test(text)) return "nginx";
    if (/^(?:SELECT\b|WITH\b|INSERT\s+INTO\b|UPDATE\s+\w+\s+SET\b|DELETE\s+FROM\b|CREATE\s+(?:TABLE|INDEX|UNIQUE|DATABASE|SCHEMA|EXTENSION|VIEW)\b|ALTER\s+TABLE\b|DROP\s+(?:TABLE|INDEX)\b|EXPLAIN\b|BEGIN\s*;|COMMIT\s*;|ROLLBACK\s*;)/im.test(text)) return "sql";
    if (/^(?:def\s+\w+\s*\(|from\s+[\w.]+\s+import\s|import\s+[\w.]+|if\s+__name__\s*==)/m.test(text)) return "python";
    if (/^[\[{]/.test(text)) {
      try { JSON.parse(text); return "json"; } catch (_) { /* Not JSON: continue with source signatures. */ }
    }
    if (/^(?:apiVersion|kind|services|scrape_configs|receivers|exporters|processors|service|groups|name|on|jobs):/m.test(text) && !/[;{}]/.test(text)) return "yaml";
    if (/^\s*#\s*(?:include|define|ifn?def|pragma)|\bstd::|\b(?:class|struct|enum|namespace|template|constexpr|consteval|static_assert)\s|\b(?:int|void|bool|char|double|float|auto|const|unsigned|size_t)\s+[\w*&]|\b(?:return|throw|co_await|co_return)\s|(?:->|\.)\w+\([^\n]*\)\s*;/m.test(text)) return "cpp";
    if (/^(?:const|let|var)\s+\w+\s*=|\bconsole\.log\s*\(|^function\s+\w+\s*\(/m.test(text)) return "javascript";
    if (/^\[[\w.-]+\]\s*$/.test(text.split("\n")[0]) && /^\w[\w.-]*\s*=/m.test(text)) return "ini";
    if (/^\w[\w.-]*\s*:\s+\S/m.test(text) && !/[;{}]/.test(text)) return "yaml";
    if (/;\s*(?:\/\/[^\n]*)?$/m.test(text) && !/^[\s\d.+-]+$/.test(text)) return stationId === "station9-sql" ? "sql" : "cpp";
    return "plaintext";
  }

  function element(create, source, attributes, language) {
    var text = String(source == null ? "" : source), props = Object.assign({}, attributes || {});
    var library = window.hljs, grammar = language || "plaintext";
    if (grammar === "plaintext" || !library || typeof library.highlight !== "function" ||
        typeof library.getLanguage !== "function") return create("code", props, text);
    try {
      if (!library.getLanguage(grammar)) return create("code", props, text);
      if (cacheLibrary !== library) { cache.clear(); cacheLibrary = library; }
      var key = grammar + "\u0000" + text, markup = cache.get(key);
      if (markup === undefined) {
        markup = library.highlight(text, { language: grammar, ignoreIllegals: true }).value;
        if (typeof markup !== "string") return create("code", props, text);
        if (cache.size >= 256) cache.delete(cache.keys().next().value);
        cache.set(key, markup);
      }
      props.className = (props.className ? props.className + " " : "") + "hljs language-" + grammar;
      props.translate = "no";
      props.dangerouslySetInnerHTML = { __html: markup };
      delete props.children;
      return create("code", props);
    } catch (_) {
      delete props.dangerouslySetInnerHTML;
      return create("code", props, text);
    }
  }

  window.CourseCode = { element: element, languageFor: languageFor };
}());
