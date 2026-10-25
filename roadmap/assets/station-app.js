(function () {
  "use strict";

  var root = document.getElementById("root");
  if (!root) return;
  if (!window.React || !window.ReactDOM) {
    root.innerHTML = '<div class="fatal"><b>Не удалось загрузить интерфейс станции.</b><br>Проверь подключение к интернету и открой страницу через локальный HTTP-сервер.</div>';
    return;
  }
  if (!window.STATION_DATA) {
    root.innerHTML = '<div class="fatal"><b>Не найдены данные станции.</b><br>Запусти tools/build_stations.py и обнови страницу.</div>';
    return;
  }

  var h = React.createElement;
  var useState = React.useState;
  var data = window.STATION_DATA;
  var meta = data.meta;
  var theory = data.theory;
  var quizzes = data.quizzes;
  var tasks = data.tasks;
  var substations = data.substations || [];
  // A theory link opens a separate tab so the quiz attempt stays mounted.
  function isWorkbook(section) { return /(?:-final-workbook|clock-worked-example)$/.test(section.id); }
  var pageParams = new URLSearchParams(window.location.hash.slice(1));
  var requestedView = ["checkpoint", "final", "quiz", "interview", "tasks", "analysis", "training"].indexOf(pageParams.get("view")) >= 0 ? pageParams.get("view") : "theory";
  var requestedModule = pageParams.get("module");
  var requestedSectionId = new URLSearchParams(window.location.hash.slice(1)).get("section");
  var requestedSection = theory.find(function (section) { return section.id === requestedSectionId; });
  var levels = { easy: "просто", medium: "средне", hard: "сложно" };
  var noteLabels = { tip: "СОВЕТ", warn: "ОСТОРОЖНО", key: "ГЛАВНОЕ" };
  var quizLabels = {
    basic: "БАЗОВЫЙ ТЕСТ",
    advanced: "УГЛУБЛЁННЫЙ ТЕСТ",
    interview: "ИНТЕРВЬЮ-ТРЕНАЖЁР",
    training: "ДОПОЛНИТЕЛЬНАЯ ТРЕНИРОВКА"
  };

  function loadStore() {
    try { return JSON.parse(localStorage.getItem(meta.storeKey)) || {}; }
    catch (_) { return {}; }
  }

  function persist(store) {
    try { localStorage.setItem(meta.storeKey, JSON.stringify(store)); }
    catch (_) { /* Прогресс необязателен: интерфейс должен работать и без storage. */ }
  }

  function scrollTop() {
    if (typeof window.scrollTo === "function") window.scrollTo({ top: 0, behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }

  function CodeBlock(props) {
    var status = useState("");
    var isOutput = /^(?:Точный вывод|Ожидаемый вывод|Вывод программы)/.test(props.block.caption || "");
    var codeRef = React.useRef(null);
    function selectCode() {
      if (!codeRef.current) return;
      var selection = window.getSelection();
      var range = document.createRange();
      range.selectNodeContents(codeRef.current);
      selection.removeAllRanges();
      selection.addRange(range);
      status[1]("Код выделен — нажмите Ctrl+C или ⌘C.");
    }
    function copy() {
      if (!navigator.clipboard || !navigator.clipboard.writeText) { selectCode(); return; }
      navigator.clipboard.writeText(props.block.code).then(function () {
        status[1]("Скопировано");
      }, selectCode);
    }
    return h("div", { className: "code-wrap" + (isOutput ? " output-wrap" : "") },
      h("div", { className: "code-toolbar" },
        h("div", { className: "code-caption" }, props.block.caption || "Фрагмент кода"),
        h("button", { className: "copy-code", onClick: copy, type: "button" }, "Копировать")),
      h("pre", { className: "code-block", tabIndex: 0, "aria-label": props.block.caption || "Фрагмент кода" }, h("code", { ref: codeRef }, props.block.code)),
      h("span", { className: "copy-status", role: "status" }, status[0]));
  }

  function splitQuestion(text) {
    var parts = String(text).split("\n\n");
    return { stem: parts[0], code: parts.slice(1).join("\n\n") };
  }

  function scoreText(result) {
    if (!result || !result.total) return "ещё не пройден";
    return result.score + "/" + result.total + " · " + Math.round(result.score / result.total * 100) + "%";
  }

  // Exact station IDs keep adjacent tracks (7Б and 9A) on their own content.
  // These references are editorial priorities, not a second question bank.
  function assessmentPriorityRefs(stationId) {
    var refs = {
      station3: ["request-memory-arena"],
      station5: ["loader-before-main"],
      "station5-linux": ["linux-mapped-generations", "linux-cpu-quota-workbook"],
      station6: ["shared-state-architecture"],
      "station9-sql": ["sql-join-multiplication", "sql-window-peers"],
      station7: ["private-public-addresses", "dhcp-network-config",
        "linux-packet-to-handler", "server-queues-two-bottlenecks", "load-balancing-connections-requests"],
      station8: ["request-execution-workbook", "architecture-boundaries",
        "dependency-fanout-workbook", "replica-state-workbook"],
      station9: ["write-lifecycle", "replication-path", "replication-failover",
        "cache-race", "cache-pressure", "outbox-transaction", "outbox-delivery"],
      station10: ["request-budget-architecture", "proxy-release-timeline"]
    };
    return (refs[stationId] || []).slice();
  }

  function assessmentFinalBudgets(stationId) {
    // 5Б keeps its complete original bank reachable. The extra memory case
    // needs the last slot more than strace, which remains in its checkpoint.
    // Exact IDs leave the C++ build station and all other tracks unchanged.
    return stationId === "station5-linux" ? {
      "os-boundary": 4, processes: 4, descriptors: 4,
      "files-storage": 4, memory: 5, "signals-limits": 4
    } : null;
  }

  function assessmentCheckpointRefs(stationId) {
    // Both new basic cases per 5Б topic are already in its final. Keep the
    // three old short checks instead of hiding them behind those additions.
    return stationId === "station5-linux" ? [] : assessmentPriorityRefs(stationId);
  }

  // Stable, balanced station-wide selection. Source banks remain untouched.
  function finalQuestions(bank, modules, limit, preferCoverage, priorityRefs, moduleBudgets) {
    // Editorial exclusions from the final exam only: these remain in chapter
    // checkpoints and source banks, but repeat a skill already tested here.
    var repeatedStems = [
      "Что делает std::move на самом деле?",
      "Функция возвращает ссылку на свой обычный локальный объект. Объект не static и не передан извне. Что происходит после выхода из функции?",
      "Base — полиморфная база. Base* указывает на живой объект, который не является Derived и не содержит подходящего подобъекта Derived. Что вернёт dynamic_cast<Derived*>(p)?",
      "Почему шаблоны обычно пишут целиком в заголовочных файлах?",
      "Поиск записи может штатно не найти её; различать причины отсутствия не требуется. Что выражает этот договор наиболее прямо?",
      "Почему исключения рекомендуют ловить как const std::exception&?",
      "std::expected<T,E> (C++23) — что это?",
      "Какой вариант в C++23 явно представляет либо разобранный Value, либо конкретную причину ParseError?",
      "Что произойдёт, если исключение выйдет наружу из деструктора, вызванного при раскрутке стека из-за другого исключения?",
      "Что обычно означает undefined reference?",
      "Компилятор поддерживает #pragma once. Что эта директива делает при включении заголовка?",
      "Что верно для std::atomic<int>?",
      "Почему condition_variable::wait требует unique_lock, а не lock_guard?",
      "Что сама по себе даёт ограниченная очередь задач при перегрузке?"
    ];
    function eligible(q) { return repeatedStems.indexOf(q.q) < 0; }
    var buckets = modules.map(function (module) {
      var basic = bank.basic.filter(function (q) { return q.substation === module.id && eligible(q); });
      var advanced = bank.advanced.filter(function (q) { return q.substation === module.id && eligible(q); });
      basic = prioritizeQuestions(basic, priorityRefs);
      var mixed = [];
      for (var i = 0; i < Math.max(basic.length, advanced.length); i++) {
        if (basic[i]) mixed.push(basic[i]);
        if (advanced[i]) mixed.push(advanced[i]);
      }
      // Promote one representative of each priority topic, rather than all
      // questions of the first topic. Some modules get only two final slots:
      // a repeated basic question must not hide the next architecture rule.
      var priorityCovered = new Set(), representatives = [], remainder = [];
      mixed.forEach(function (question) {
        var refs = (question.theoryRefs || []).filter(function (ref) {
          return (priorityRefs || []).indexOf(ref) >= 0;
        });
        if (refs.some(function (ref) { return !priorityCovered.has(ref); })) {
          representatives.push(question);
          refs.forEach(function (ref) { priorityCovered.add(ref); });
        } else {
          remainder.push(question);
        }
      });
      return representatives.concat(remainder);
    });
    var selected = [], covered = new Set(), moduleCounts = modules.map(function () { return 0; });
    function available(bucket, index) {
      var budget = moduleBudgets && moduleBudgets[modules[index].id];
      return bucket.length && (budget === undefined || budget === null || moduleCounts[index] < budget);
    }
    while (selected.length < limit && buckets.some(available)) {
      buckets.forEach(function (bucket, moduleIndex) {
        if (!available(bucket, moduleIndex) || selected.length >= limit) return;
        // Within each chapter, prefer a rule not already tested. Keep the
        // basic/advanced order as the stable tie-breaker, not random sampling.
        var index = preferCoverage ? bucket.findIndex(function (question) {
          return (question.theoryRefs || []).some(function (ref) { return !covered.has(ref); });
        }) : 0;
        var question = bucket.splice(index < 0 ? 0 : index, 1)[0];
        selected.push(question);
        moduleCounts[moduleIndex]++;
        (question.theoryRefs || []).forEach(function (ref) { covered.add(ref); });
      });
    }
    return selected;
  }

  // Selection belongs to the assessment, not to physical bank order. Keep
  // historical question positions stable for readers and source checks.
  function prioritizeQuestions(questions, refs) {
    if (!refs || !refs.length) return questions;
    function priority(q) { return refs.some(function (ref) { return (q.theoryRefs || []).indexOf(ref) >= 0; }); }
    return questions.filter(priority).concat(questions.filter(function (q) { return !priority(q); }));
  }

  function chapterQuestions(bank, id, refs) {
    return prioritizeQuestions((bank.basic || []).filter(function (q) { return q.substation === id; }), refs).slice(0, 3);
  }

  // Training exposes every authored position, including questions deliberately
  // excluded from the short exam. Do not deduplicate or randomly sample it.
  function trainingEntries(bank, moduleId, kind) {
    var kinds = kind === "basic" || kind === "advanced" ? [kind] : ["basic", "advanced"];
    return kinds.reduce(function (entries, sourceKind) {
      return entries.concat((bank[sourceKind] || []).map(function (question, index) {
        return { id: sourceKind + ":" + index, kind: sourceKind, question: question };
      }).filter(function (entry) { return !moduleId || entry.question.substation === moduleId; }));
    }, []);
  }

  function trainingSettings(params, modules) {
    var moduleId = params.get("module") || "";
    var kind = params.get("kind");
    var size = Number(params.get("size")), batch = Number(params.get("set"));
    return {
      module: modules.some(function (module) { return module.id === moduleId; }) ? moduleId : "",
      kind: kind === "basic" || kind === "advanced" ? kind : "all",
      size: [5, 10, 15].indexOf(size) >= 0 ? size : 10,
      batch: Number.isSafeInteger(batch) && batch >= 1 ? batch - 1 : null
    };
  }

  function trainingHash(settings) {
    var hash = "#view=training";
    if (settings.module) hash += "&module=" + encodeURIComponent(settings.module);
    if (settings.kind !== "all") hash += "&kind=" + settings.kind;
    if (settings.size !== 10) hash += "&size=" + settings.size;
    if (settings.batch !== null) hash += "&set=" + (settings.batch + 1);
    return hash;
  }

  function trainingBatches(entries, size) {
    size = [5, 10, 15].indexOf(size) >= 0 ? size : 10;
    var batches = [];
    for (var start = 0; start < entries.length; start += size) batches.push(entries.slice(start, start + size));
    return batches;
  }

  function trainingResultKey(entries) {
    return entries.length ? "station-training:v1:" + entries.map(function (entry) { return entry.id; }).join("|") : "";
  }

  // Keep the original task data (including hints and solutions) intact.
  // These tasks require constructing or repairing a solution; the rest are
  // open-answer checks and belong alongside the station test.
  function isPracticeTask(task) {
    if (task.level === "Практика" && task.title.indexOf("Лаборатория: ") === 0) return true;
    if (task.level === "Практика" && task.title.indexOf("Эксплуатация: ") === 0) return true;
    if (["Пользователи без задач", "По одной задаче владельца", "Отчёт для API", "SQL с нуля: 20 упражнений в браузере"].indexOf(task.title) >= 0) return true;
    return ["Найти гонку и исправить двумя способами", "Потокобезопасный класс",
      "shared_mutex: кэш метрик", "Исправить deadlock", "Ожидание данных через condition_variable",
      "Результат из потока через future", "Передача исключения между потоками",
      "Ограничение параллелизма семафором", "latch: дождаться группы задач",
      "barrier: синхронные фазы сбора", "Собери всё: параллельный сбор телеметрии",
      "Ограниченная очередь: закрытие без потери принятого", "Пул потоков: очередь, результаты и два режима остановки",
      "Расследование гонки с ThreadSanitizer", "Итоговый сервис: составь проверяемое описание",
      "План эксперимента: очередь при перегрузке и восстановлении", "PostgreSQL: конкурентное место и восстановление", "SQL: отчёт без потерянных пользователей", "PostgreSQL: сравни планы на ста тысячах строк", "SQL с нуля: 14 упражнений в браузере"].indexOf(task.title) >= 0;
  }

  function PracticeLinks() {
    var catalog = {
      10: [["Google Test · официальный primer", "https://google.github.io/googletest/primer.html", "После задач учебника перенеси проверки Gate в TEST и добавь fixture. Локально нужны CMake, компилятор и Google Test. Проверь, что неверное ожидание даёт неуспешный CTest и в Debug, и в Release."]],
      0: [["1603 · Design Parking System", "design-parking-system", "Класс, конструктор и изменение состояния через методы. Проверь отсутствие мест и независимость трёх счётчиков. Это задача на инвариант, а не на наследование."]],
      1: [["Exercism · Simple Linked List", "https://github.com/exercism/cpp/tree/main/exercises/practice/simple-linked-list", "Реализуй односвязный список по интерфейсу и тестам упражнения. Это практика владения узлами и освобождения памяти, а не задача на скорость алгоритма. Понадобятся указатели и локальный C++-проект; для запуска тестов пригодится станция 5. Критерий: тесты проходят, пустой список и удаление последнего элемента обработаны. Дополнение нашего курса: явно задай политику копирования и перемещения; не оставляй случайное поверхностное копирование владеющего указателя. Это дополнение, а не требование исходного упражнения."]],
      2: [["LearnCpp · Shape, Circle и Triangle (задание 2)", "https://www.learncpp.com/cpp-tutorial/chapter-25-summary-and-quiz/", "На странице выбери задание 2, а не вопросы на предсказание вывода. Напиши абстрактный интерфейс и две реализации с виртуальной печатью. Нужны наследование, override и основы operator<<; этот оператор можно изучить по предоставленному каркасу. Решай в локальном компиляторе, решение для сверки раскрывается на странице. Критерий: печать через общий интерфейс, корректное разрушение объектов. Важная поправка к соседнему ответу 1f: обычное delete через базовый указатель без необходимого виртуального деструктора — неопределённое поведение, а не гарантированная «утечка производной части»."]],
      3: [["622 · Design Circular Queue", "design-circular-queue", "Реализуй кольцевую очередь без готовой очереди. Проверь пустое и полное состояние, переход через конец буфера и размер 1."], ["347 · Top K Frequent Elements", "top-k-frequent-elements", "Примени подсчёт частот и выбор наиболее частых элементов. Сравни сложность сортировки, кучи и группировки по частоте."]],
      4: [["LearnCpp · Fraction и отказ конструктора", "https://www.learncpp.com/cpp-tutorial/chapter-27-summary-and-quiz/", "Практическое задание в конце главы: реализуй дробь и обработку недопустимого знаменателя через исключение. Нужны конструкторы, std::exception и вывод в поток. Проверка локальная; на странице есть решение. Дополнение нашего курса: раздели ошибку чтения числа и отказ конструктора, протестируй нулевой и ненулевой знаменатель. Это небольшое упражнение на сигнализацию отказа, не полная проверка exception safety; обобщения в окружающем тексте не заменяют правила из нашей теории."]],
      5: [["CMake · Getting Started, упражнения 1–3", "https://cmake.org/cmake/help/latest/guide/tutorial/Getting%20Started%20with%20CMake.html", "Официальный практикум: собери исполняемый файл, создай библиотеку и свяжи их через target_link_libraries. Выполняй упражнения по порядку на локальной машине с компилятором и версией CMake, указанной в текущем tutorial. Страница latest обновляется и может требовать более новый CMake, чем примеры учебника. Критерий: проект собирается из отдельного пустого build-каталога; ты можешь объяснить, какие цели создаются, какие исходники в них входят и как передаются требования к заголовкам."]],
      6: [["1114 · Print in Order", "print-in-order", "Согласуй три потока независимо от порядка их запуска. Не используй sleep как средство синхронизации; объясни условие, которое позволяет каждому потоку продолжить работу."]],
      7: [["Stanford CS144 · Checkpoint 0: webget и ByteStream", "https://cs144.github.io/assignments/check0.pdf", "Два последовательных задания на C++: HTTP-клиент поверх TCP и ограниченный поток байтов в памяти. Сначала настрой окружение и стартовый проект по инструкции CS144, затем выполни разделы 5.5 и 6. Нужны Linux, Git, CMake и материал станции 7; это лабораторная, не пятиминутная задача в браузере. Критерий: проверки check_webget и check0 из соответствующей редакции задания. ByteStream здесь однопоточный: не добавляй блокировки без причины. Полная реализация TCP в следующих лабораторных — отдельное углубление, не обязательный минимум."]],
      9: [["PostgreSQL · официальный практикум SQL", "https://www.postgresql.org/docs/18/tutorial-sql.html", "Пройди создание таблиц, заполнение, JOIN и агрегаты на локальной учебной базе. Затем выполни лабораторную курса ниже: два соединения, конфликт записи и восстановление. Нужны PostgreSQL 18 и psql; критерии результата и изолированное окружение описаны в examples/station9/README.md."]],
      8: [["Full Stack Open · Phonebook backend, упражнения 3.1–3.6", "https://fullstackopen.com/en/part3/node_js_and_express/#exercises-3-1-3-6", "Оригинальный практикум использует JavaScript, Node.js и Express. Для нашего курса это адаптация требований на C++: реализуй HTTP API телефонной книги на серверной библиотеке станции 8, а не переписывай команды npm. Понадобятся JSON, маршрутизация, валидация и локальные запросы через curl или HTTP-клиент. Критерий нашей адаптации: чтение списка и записи, создание и удаление, понятные ошибки и проверка дубликатов. Случайные ID из вводного примера не переноси как гарантию уникальности — выбери явный договор. Автоматическая проверка курса для C++-версии не обещается."]]
    };
    var entries = catalog[meta.number] || [];
    if (meta.id === "station5-linux") entries = [["Linux man-pages · программы из pipe(2)", "https://man7.org/linux/man-pages/man2/pipe.2.html", "После итогового разбора воспроизведи пример канала из раздела EXAMPLES в отдельном учебном каталоге Linux. Затем измени передачу одного байта на поток из нескольких порций и объясни, какие закрытия нужны для EOF. Это адаптация практики по контракту API, не онлайн-проверка. Не запускай упражнения от root и не направляй сигналы чужим процессам."]];
    if (meta.id === "station7-netlab") entries = [["iproute2 · network namespaces", "https://man7.org/linux/man-pages/man8/ip-netns.8.html", "Сопоставь официальный пример с четырьмя узлами учебного стенда. Настройки разрешены только внутри одноразовой VM; для разбора без запуска составь карту интерфейсов, маршрутов и времени жизни namespace. Не переноси физические интерфейсы и не повторяй из внешних примеров массовую очистку или kill."]];
    if (meta.id === "station7-traffic") entries = [["Wireshark · Follow Stream и TCP Analysis", "https://www.wireshark.org/docs/wsug_html_chunked/ChapterAdvanced.html", "Открой учебные PCAP из станции, восстанови HTTP-обмен и составь отчёт: наблюдение, гипотеза, недостающая проверка. Затем сравни свои выводы с официальным описанием анализа TCP. Это работа с файлами, а не захват чужого трафика; устанавливать Wireshark для чтения готового разбора не обязательно."]];
    if (meta.id === "station9-sql") entries = [["PostgreSQL · официальный практикум SQL", "https://www.postgresql.org/docs/18/tutorial-sql.html", "Для локальной практики PostgreSQL пройди таблицы, запросы и агрегаты. Встроенные задания этой станции можно решать в SQL-тренажёре; транзакционная лабораторная относится к следующей станции 9B."]];
    return h("section", { className: "practice-links" }, h("h2", null, "Практика"),
      h("p", { className: "section-lead" }, "Здесь нужно самостоятельно построить решение, а не выбрать готовый ответ."),
      ["station8", "station9", "station10"].indexOf(meta.id) >= 0 ? h(ServiceWorkshopEntry) : null,
      entries.length ? h("div", null,
        h("p", { className: "notes" }, "Внешняя практика: LeetCode, открытые курсы и лабораторные. У каждой задачи указаны границы и способ работы. Материалы преимущественно на английском; часть требует локального компилятора, а платформы могут попросить вход."),
        entries.map(function (entry) { return h("article", { className: "finale-item", key: entry[1] },
          h("h3", null, h("a", { href: entry[1].indexOf("https://") === 0 ? entry[1] : "https://leetcode.com/problems/" + entry[1] + "/", target: "_blank", rel: "noopener noreferrer" }, entry[0] + " ↗")), h("p", null, entry[2])); }))
        : h("p", { className: "notes" }, "Для этой станции подходящая подборка LeetCode пока не добавлена: алгоритмическая задача не заменяет проверку владения, исключений, сборки или серверного протокола. Учебный проект станции описан на главной странице курса."),
      h("p", { className: "notes" }, "После решения объясни инвариант, граничные случаи и ограничения своего подхода. Успешная отправка — проверка тестов платформы, а не всей теории станции."));
  }

  function VisualBlock(props) {
    var block = props.block;
    return h("figure", { className: "network-visual visual-" + block.variant },
      h("div", { className: "visual-head" },
        h("figcaption", null, block.title),
        h("span", null, block.eyebrow || "СХЕМА")),
      h("div", { className: "visual-items" }, block.items.map(function (entry, index) {
        return h("div", { className: "visual-item", key: index },
        h("span", { className: "visual-label" }, entry.label),
        h("strong", null, entry.title),
        h("div", { className: "visual-item-text", dangerouslySetInnerHTML: { __html: entry.html } }));
      })),
      block.caption ? h("p", { className: "visual-caption" }, block.caption) : null);
  }

  function PacketBlock(props) {
    var block = props.block;
    var state = useState(0);
    var active = state[0], setActive = state[1];
    var layers = block.layers.slice(0, active);
    var total = block.payload.bytes;
    layers.forEach(function (layer) {
      total += layer.headerBytes + (layer.trailerBytes || 0);
    });
    var headers = layers.slice().reverse().map(function (layer, index) {
      return h("div", {
        className: "packet-segment packet-header packet-color-" + ((layers.length - index) % 5),
        key: "h:" + layer.label,
        style: { flexGrow: Math.max(layer.headerBytes, 8) }
      }, h("strong", null, layer.label), h("span", null, layer.headerBytes + " B"));
    });
    var trailers = layers.filter(function (layer) { return layer.trailerBytes; }).map(function (layer, index) {
      return h("div", {
        className: "packet-segment packet-trailer packet-color-" + ((index + 3) % 5),
        key: "t:" + layer.label,
        style: { flexGrow: Math.max(layer.trailerBytes, 8) }
      }, h("strong", null, layer.label + " trailer"), h("span", null, layer.trailerBytes + " B"));
    });
    var current = active === 0 ? null : block.layers[active - 1];
    return h("figure", { className: "packet-lab" },
      h("div", { className: "visual-head" },
        h("figcaption", null, block.title),
        h("span", null, "ПОШАГОВАЯ ИНКАПСУЛЯЦИЯ")),
      h("p", { className: "packet-assumption" }, block.assumption),
      h("div", { className: "packet-controls" }, [
        { label: "Данные приложения", title: block.payload.label }
      ].concat(block.layers.map(function (layer) {
        return { label: layer.label, title: layer.title };
      })).map(function (entry, index) {
        return h("button", {
          className: "packet-step" + (index === active ? " active" : ""),
          key: index,
          "aria-pressed": index === active,
          onClick: function () { setActive(index); }
        }, h("span", null, index), h("strong", null, entry.label), h("small", null, entry.title));
      })),
      h("div", { className: "packet-result" },
        h("div", { className: "packet-result-head" },
          h("strong", null, active === 0 ? "Application data" : current.result),
          h("span", null, total + " bytes")),
        h("div", { className: "packet-bar", "aria-label": "Состав блока данных" },
          headers,
          h("div", { className: "packet-segment packet-payload", style: { flexGrow: block.payload.bytes } },
            h("strong", null, block.payload.label), h("span", null, block.payload.bytes + " B")),
          trailers),
        h("div", { className: "packet-scale" },
          h("span", null, "первый byte"), h("span", null, "последний byte"))),
      h("div", { className: "packet-explanation" }, current
        ? h("div", null,
            h("strong", null, current.title + ": +" + (current.headerBytes + (current.trailerBytes || 0)) + " bytes"),
            h("p", { dangerouslySetInnerHTML: { __html: current.html } }))
        : h("div", null,
            h("strong", null, block.payload.label + ": " + block.payload.bytes + " bytes"),
            h("p", null, block.payload.html))),
      block.caption ? h("p", { className: "visual-caption" }, block.caption) : null);
  }

  function ExchangeBlock(props) {
    var block = props.block;
    return h("figure", { className: "exchange-diagram" },
      h("div", { className: "visual-head" },
        h("figcaption", null, block.title), h("span", null, "ОБМЕН НА ПРОВОДЕ")),
      h("div", { className: "exchange-actors" }, h("strong", null, block.left), h("strong", null, block.right)),
      h("div", { className: "exchange-steps" }, block.steps.map(function (step, index) {
        var leftToRight = step.from === "left";
        return h("div", { className: "exchange-step " + (leftToRight ? "to-right" : "to-left"), key: index },
          h("div", { className: "exchange-index" }, index + 1),
          h("div", { className: "exchange-message" },
            h("div", { className: "exchange-arrow" }, leftToRight ? "→" : "←"),
            h("strong", null, step.label + " · " + step.title),
            h("p", { dangerouslySetInnerHTML: { __html: step.html } })));
      })),
      block.caption ? h("p", { className: "visual-caption" }, block.caption) : null);
  }

  function LanesBlock(props) {
    var block = props.block;
    var fields = block.mode === "fields";
    return h("figure", { className: "lanes-diagram" },
      h("div", { className: "visual-head" },
        h("figcaption", null, block.title), h("span", null, fields ? "СРАВНЕНИЕ ПОЛЕЙ" : "ПОТОКИ ВО ВРЕМЕНИ")),
      h("div", { className: "lanes-axis" },
        h("span", null, fields ? "канальное обрамление" : "раньше"),
        h("span", null, fields ? "вложенные данные" : "позже")),
      h("div", { className: "lanes-list" }, block.lanes.map(function (lane, laneIndex) {
        return h("div", { className: "lane-row", key: laneIndex },
          h("div", { className: "lane-label" }, h("strong", null, lane.label), h("span", null, lane.title)),
          h("div", { className: "lane-track" }, lane.segments.map(function (segment, segmentIndex) {
            return h("span", { className: "lane-segment lane-color-" + (segmentIndex % 4), key: segmentIndex }, segment);
          })),
          h("p", { dangerouslySetInnerHTML: { __html: lane.html } }));
      })),
      block.caption ? h("p", { className: "visual-caption" }, block.caption) : null);
  }

  function LabBlock(props) {
    var catalog = window.COURSE_LABS || [];
    var lab = catalog.find(function (item) { return item.id === props.block.lab; });
    var entry = lab && lab.entries.find(function (entry) {
      return entry.station === meta.id && entry.section === props.section.id && entry.scenario === props.block.scenario;
    });
    if (!entry || !window.courseLabHref) return null;
    return h("aside", { className: "course-lab-entry", "aria-label": entry.title },
      h("span", { className: "course-lab-eyebrow" }, "ВИЗУАЛЬНЫЙ ЭКСПЕРИМЕНТ"),
      h("h3", null, entry.title), h("p", null, entry.description),
      h("a", { href: window.courseLabHref(lab.id, entry.scenario, meta.id, props.section.id), target: "_blank", rel: "noopener noreferrer" }, "Открыть лабораторию ↗"),
      h("small", null, "В новой вкладке · возврат к этому разделу внутри лаборатории"));
  }

  function ServiceWorkshopEntry() {
    var stage = { station8: "local", station9: "database", station10: "vm" }[meta.id];
    if (!stage) return null;
    return h("aside", { className: "course-lab-entry", "aria-label": "Сквозной серверный практикум" },
      h("span", { className: "course-lab-eyebrow" }, "РЕАЛЬНЫЙ ПРОЕКТ · ЛОКАЛЬНО И НА LINUX-VM"),
      h("h3", null, "Свой C++-сервис: от localhost до сервера"),
      h("p", null, "Пошаговый маршрут с исходниками: сборка API, запросы curl, PostgreSQL, Docker Compose, SSH-туннель и необязательный VPS/HTTPS. У каждой команды указано место выполнения."),
      h("a", { href: "service_workshop.html#" + stage, target: "_blank", rel: "noopener noreferrer" }, "Открыть практикум ↗"),
      h("small", null, "Нужен свой Linux-терминал · команды не исполняются в браузере · возвращайся к этапам по мере прохождения станций 8–10"));
  }

  function SubstationNav(props) {
    var contentsState = useState(function () { return window.matchMedia("(min-width: 1001px)").matches; });
    var searchState = useState("");
    var query = searchState[0].trim().toLocaleLowerCase("ru");
    function sectionMatches(section) {
      if (section.title.toLocaleLowerCase("ru").includes(query)) return true;
      return section.blocks.some(function (block) {
        if (block.type !== "lab") return false;
        var lab = (window.COURSE_LABS || []).find(function (item) { return item.id === block.lab; });
        var entry = lab && lab.entries.find(function (item) { return item.station === meta.id && item.section === section.id && item.scenario === block.scenario; });
        return entry && (entry.title + " " + entry.description).toLocaleLowerCase("ru").includes(query);
      });
    }
    var visibleItems = props.items.filter(function (entry) {
      return !query || (entry.label + " " + entry.title).toLocaleLowerCase("ru").includes(query) || theory.some(function (section) {
        return section.substation === entry.id && sectionMatches(section);
      });
    });
    var stationRouteHints = {
      station0: "Начни с устройства объекта и правил допустимого состояния. Затем разбери создание, уничтожение и выбор доступных пользователю операций.",
      station1: "Сначала выясни, кто удерживает объект живым и освобождает ресурс. Затем разбери доступ без владения, копирование и перемещение.",
      station2: "Начни с отношений между базовым и производным классами. Затем проследи создание их частей, выбор вызываемого метода и безопасное уничтожение.",
      station3: "Выбирай контейнер под данные и операции. После этого переходи к алгоритмам, шаблонам и типам для представления значений и диапазонов.",
      station4: "Сначала определи смысл отказа. Затем проследи исключение, проверь состояние после ошибки и выбери, где её обрабатывать.",
      station5: "Проследи путь от исходного файла до работающего процесса. Затем разбери CMake, повторяемость сборки и поиск причин сбоев.",
      station6: "Для первого прохода используй маршрут из начала 6.1: к формальным блокам 6.2 и 6.4 лучше вернуться после mutex, ожиданий и future."
    };
    return h("details", { className: "substation-shell", open: contentsState[0], onToggle: function (event) { contentsState[1](event.currentTarget.open); }, "aria-label": "Оглавление станции" },
      h("summary", { className: "contents-toggle" }, "Оглавление станции"),
      h("a", { className: "course-home", href: "cpp_backend_roadmap.html" }, "← C++ и backend"),
      meta.number === 9 ? h("a", { className: "course-home", href: meta.id === "station9-sql" ? "cpp_station9_databases.html" : "cpp_station9_sql.html" }, meta.id === "station9-sql" ? "Далее: 9B · PostgreSQL →" : "← 9A · SQL с нуля") : null,
      meta.number === 9 ? h("a", { className: "sql-trainer-entry", href: "sql_trainer.html", target: "_blank", rel: "noopener" },
        h("span", { className: "sql-trainer-icon", "aria-hidden": true }, "SQL"),
        h("span", null, h("strong", null, "SQL-тренажёр"), h("small", null, "Запросы на практике")),
        h("span", { className: "sql-trainer-arrow", "aria-hidden": true }, "↗"),
        h("span", { className: "sql-trainer-sr" }, " — в новой вкладке")) : null,
      h("div", { className: "substation-heading" },
        h("div", null, h("span", null, meta.logo), h("h2", null, "Содержание")),
        h("p", null, stationRouteHints[meta.id] || "Проходи последовательно: каждая следующая использует модель предыдущей.")),
      h("label", { className: "contents-search" }, h("span", null, "Найти раздел"),
        h("input", { type: "search", value: searchState[0], placeholder: "Например, конструктор", onChange: function (event) { searchState[1](event.target.value); } })),
      query ? h("p", { className: "search-result-count", role: "status" }, visibleItems.length ? "Подстанций найдено: " + visibleItems.length : "Совпадений нет. Попробуйте другое название.") : null,
      h("div", { className: "substation-grid" }, visibleItems.map(function (entry) {
        var moduleSections = theory.filter(function (section) { return section.substation === entry.id && !isWorkbook(section); });
        var completed = moduleSections.filter(function (section) { return props.store["sec:" + section.id]; }).length;
        var isActive = entry.id === props.active;
        return h("div", { key: entry.id }, h("button", {
          className: "substation-card" + (isActive ? " active" : ""),
          key: entry.id,
          "aria-pressed": isActive,
          onClick: function () { props.onChoose(entry.id); }
        },
        h("span", { className: "substation-number" }, entry.label),
        h("span", { className: "substation-title" }, entry.title),
        h("span", { className: "substation-subtitle" }, entry.subtitle),
        h("span", { className: "substation-progress" }, completed + "/" + moduleSections.length + " отмечено")),
        (isActive || query) ? h("nav", { className: "contents-sections", "aria-label": entry.title }, moduleSections.filter(function (section) {
          return !query || (entry.label + " " + entry.title).toLocaleLowerCase("ru").includes(query) || sectionMatches(section);
        }).map(function (section) {
          var current = props.view === "theory" && isActive && section.id === (props.selected || moduleSections[0].id);
          return h("div", { key: section.id, className: "contents-section-with-labs" }, h("button", { "aria-current": current ? "page" : undefined,
            onClick: function () { props.onNavigate(section.id); } },
            props.store["sec:" + section.id] ? "✓ " : "", section.title),
            section.blocks.filter(function (block) { return block.type === "lab"; }).map(function (block) {
              var lab = (window.COURSE_LABS || []).find(function (item) { return item.id === block.lab; });
              var entry = lab && lab.entries.find(function (entry) { return entry.station === meta.id && entry.section === section.id && entry.scenario === block.scenario; });
              return entry && window.courseLabHref ? h("a", { key: block.lab, className: "contents-lab-link", href: window.courseLabHref(lab.id, entry.scenario, meta.id, section.id), target: "_blank", rel: "noopener noreferrer" }, entry.title, " ↗") : null;
            }));
        }), h("button", { className: "contents-checkpoint", "aria-current": isActive && props.view === "checkpoint" ? "page" : undefined, onClick: function () { props.onCheckpoint(entry.id); } }, "Закрепление подглавы")) : null);
      })),
      h("nav", { className: "contents-ending", "aria-label": "Завершение станции" },
        h("button", { "aria-current": props.view === "final" ? "page" : undefined, onClick: function () { props.onPage("final"); } }, "Завершение станции")),
      ["station8", "station9", "station10"].indexOf(meta.id) >= 0 ? h("a", { href: "service_workshop.html#" + ({station8:"local", station9:"database", station10:"vm"}[meta.id]), className: "contents-all-labs", target: "_blank", rel: "noopener noreferrer" }, "Свой сервер · сквозной практикум ↗") : null,
      h("a", { href: "visual_labs.html", className: "contents-all-labs" }, "Все визуальные лаборатории →"),
      h("a", { href: "glossary.html", className: "contents-all-labs", target: "_blank", rel: "noopener" }, "Глоссарий терминов ↗"));
  }

  function Theory(props) {
    var state = useState(function () {
      var index = props.sections.findIndex(function (section) { return section.id === props.initialSectionId; });
      return index < 0 ? 0 : index;
    });
    var active = state[0];
    var setActive = state[1];
    var sections = props.sections;
    var section = sections[active];
    React.useEffect(function () {
      try {
        localStorage.setItem("cpp_course_last_read_v1", JSON.stringify({ file: meta.sourceFile, section: section.id, title: section.title, station: meta.number }));
      } catch (_) { /* Reading remains available without storage. */ }
    }, [section.id]);
    var routeIndex = props.readingOrder ? props.readingOrder.indexOf(section.id) : -1;
    var nextRouteId = routeIndex >= 0 ? props.readingOrder[routeIndex + 1] : null;
    var nextRouteSection = nextRouteId ? theory.find(function (item) { return item.id === nextRouteId; }) : null;

    function openSection(index) {
      props.onNavigate(sections[index].id);
    }

    return h("div", null,
      h("div", { className: "section-nav legacy-section-nav" }, sections.map(function (item, index) {
        var done = !!props.store["sec:" + item.id];
        return h("button", {
          className: "pill" + (index === active ? " active" : ""),
          key: item.id,
          onClick: function () { openSection(index); }
        },
        h("span", { className: "section-dot" + (done ? " done" : "") }, done ? "✓" : ""),
        (index + 1) + ". " + item.title);
      })),
      h("article", { className: "card fade-in", key: section.id, "data-terms-scope": section.id },
        h("nav", { className: "reading-breadcrumbs", "aria-label": "Положение в курсе" },
          h("a", { href: "cpp_backend_roadmap.html" }, "Курс"), h("span", { "aria-hidden": true }, "/"),
          h("span", null, "Станция " + (meta.id === "station5-linux" ? "5Б" : meta.id === "station7-netlab" ? "7Б" : meta.id === "station7-traffic" ? "7В" : meta.number === 9 ? (meta.id === "station9-sql" ? "9A" : "9B") : meta.number)), h("span", { "aria-hidden": true }, "/"),
          h("span", { "aria-current": "location" }, "Теория")),
        h("div", { className: "kicker" }, routeIndex >= 0 ? "ПЕРВОЕ ЧТЕНИЕ · ШАГ " + (routeIndex + 1) + " / " + props.readingOrder.length : "РАЗДЕЛ " + (active + 1) + " / " + sections.length),
        h("h2", { className: "section-title" }, section.title),
        h("p", { className: "section-lead" }, section.lead),
        meta.number === 9 && ["tables", "queries", "aggregation", "composition", "windows", "backend-sql"].indexOf(section.substation) >= 0 && section.id !== "sql-trainer" ? h("p", { className: "sql-practice-link" },
          h("a", { href: "sql_trainer.html#" + ({ "sql-language": "expression", "sql-first-query": "expression", "sql-create-basics": "insert", "sql-select-basics": "columns", "sql-filter-basics": "filter", "sql-null-basics": "null", "sql-order-basics": "sort", "sql-write-basics": "update", "sql-join-basics": "join", "worked-example": "join", "sql-aggregate-basics": "group", "aggregation": "having", "join-shapes": "left", "sql-exists": "exists", "sql-cte-union": "cte", "sql-window-rank": "window", "sql-window-frame": "frame", "sql-backend-boundaries": "upsert", "sql-report-final-workbook": "report" }[section.id] || "columns"), target: "_blank", rel: "noopener" }, "Попробовать в SQL-тренажёре ↗"),
          h("span", null, "В новой вкладке — место в учебнике сохранится")) : null,
        section.blocks.map(function (block, index) {
          if (block.type === "lab") {
            return h(LabBlock, { block: block, section: section, key: index });
          }
          if (block.type === "sql-trainer") {
            var trainerUrl = "sql_trainer.html#" + encodeURIComponent(block.exercise);
            return h("div", { key: index, className: "sql-trainer-embed" },
              h("a", { className: "sql-trainer-launch", href: trainerUrl, target: "_blank", rel: "noopener noreferrer" }, "Открыть SQL-тренажёр ↗"),
              h("iframe", { src: trainerUrl, title: "SQL с нуля: редактор запросов и учебные таблицы", loading: "lazy", style: { width: "100%", height: "1100px", border: "1px solid #dce3e9", borderRadius: "8px", marginTop: "16px" } }));
          }
          if (block.type === "text") {
            return h("p", { className: "theory-text", key: index, dangerouslySetInnerHTML: { __html: block.html } });
          }
          if (block.type === "code") {
            return h(CodeBlock, { key: section.id + ":" + index, block: block });
          }
          if (block.type === "note") {
            var isSource = /^\s*<(?:b|strong)>[^<]*(?:[Ии]сточник|[Пп]ервоисточник|Основание и границы)/.test(block.html || "");
            return h("div", { className: "note " + (isSource ? "source-note" : (block.kind || "key")), key: index },
              h("span", { className: "note-label" }, isSource ? "ИСТОЧНИКИ И ГРАНИЦЫ ПРИМЕНЕНИЯ" : (noteLabels[block.kind] || noteLabels.key)),
              h("span", { className: "note-text", dangerouslySetInnerHTML: { __html: block.html } }));
          }
          if (block.type === "diagram") {
            return h("figure", { className: "diagram diagram-" + (block.mode || "flow"), key: index },
              h("figcaption", { className: "diagram-title" }, block.title),
              h("div", { className: "diagram-items" }, block.items.map(function (item, itemIndex) {
                return h("div", { className: "diagram-item", key: itemIndex },
                  h("span", { className: "diagram-index", "aria-hidden": "true" }, itemIndex + 1),
                  h("strong", { dangerouslySetInnerHTML: { __html: item.title } }),
                  h("p", { dangerouslySetInnerHTML: { __html: item.html } }));
              })),
              block.caption ? h("p", { className: "diagram-caption" }, block.caption) : null);
          }
          if (block.type === "visual") {
            return h(VisualBlock, { block: block, key: index });
          }
          if (block.type === "packet") {
            return h(PacketBlock, { block: block, key: index });
          }
          if (block.type === "exchange") {
            return h(ExchangeBlock, { block: block, key: index });
          }
          if (block.type === "lanes") {
            return h(LanesBlock, { block: block, key: index });
          }
          return null;
        }),
        ((meta.id === "station8" && section.id === "httplib-example") || (meta.id === "station9" && section.id === "cpp-storage") || (meta.id === "station10" && section.id === "docker-network-data")) ? h(ServiceWorkshopEntry) : null,
        h("div", { className: "section-actions" },
          h("button", {
            className: "primary" + (props.store["sec:" + section.id] ? " done" : ""),
            onClick: function () { props.toggleSection(section.id); }
          }, props.store["sec:" + section.id] ? "✓ Раздел изучен" : "Отметить раздел изученным"),
          active > 0 ? h("button", { className: "secondary", onClick: function () { openSection(active - 1); } }, "← Назад") : null,
          active < sections.length - 1
            ? h("button", { className: "secondary", onClick: function () { openSection(active + 1); } }, "Далее: " + sections[active + 1].title + " →")
            : h("button", { className: "secondary", onClick: props.onComplete }, isWorkbook(section) ? "Далее: итоговый тест →" : "Далее: закрепление подглавы →"))));
  }

  function QuizPicker(props) {
    var choices = [
      { id: "basic", label: "БАЗОВЫЙ", title: "Проверка понимания", text: "Вопросы по ключевым понятиям и примерам из теории.", result: props.results.basic },
      { id: "advanced", label: "УГЛУБЛЁННЫЙ", title: "Разбор тонких мест", text: "Более сложные сценарии: время жизни, гарантии, крайние случаи и дизайн.", result: props.results.advanced }
    ];
    if (props.final) choices = [{ id: "basic", label: "ИТОГ СТАНЦИИ", title: "Общий тест", text: "25 вопросов по разным подстанциям: основные понятия и применение правил.", result: props.results.basic }];
    if (props.quizzes.interview && props.quizzes.interview.length) {
      choices.push({
        id: "interview",
        label: "MIDDLE+",
        title: "Интервью-тренажёр",
        text: "Разбери код или рабочую ситуацию: определи результат, найди ошибку и объясни, какое правило нарушено.",
        result: props.results.interview
      });
    }
    return h("div", { className: "quiz-picker" }, choices.map(function (choice) {
      return h("button", {
        className: "quiz-choice " + choice.id,
        key: choice.id,
        onClick: function () { props.onChoose(choice.id); }
      },
      h("div", { className: "quiz-choice-label" }, choice.label),
      h("h2", null, choice.title),
      h("p", null, choice.text),
      h("div", { className: "quiz-choice-meta" },
        h("span", null, "Вопросов: " + props.quizzes[choice.id].length),
        h("span", { className: choice.result ? "quiz-choice-score" : "" }, scoreText(choice.result))));
    }));
  }

  // Shuffle options once per attempt, never on a re-render. Keep question order
  // so a sequence of teaching examples still builds on the preceding question.
  function prepareQuestions(questions) {
    return questions.map(function (question) {
      var order = question.options.map(function (_, index) { return index; });
      for (var i = order.length - 1; i > 0; i--) {
        var j = Math.floor(Math.random() * (i + 1));
        var saved = order[i]; order[i] = order[j]; order[j] = saved;
      }
      return Object.assign({}, question, {
        options: order.map(function (index) { return question.options[index]; }),
        answer: order.indexOf(question.answer)
      });
    });
  }

  function Quiz(props) {
    var idxState = useState(0);
    var idx = idxState[0], setIdx = idxState[1];
    var selectedState = useState(null);
    var selected = selectedState[0], setSelected = selectedState[1];
    var scoreState = useState(0);
    var score = scoreState[0], setScore = scoreState[1];
    var doneState = useState(false);
    var done = doneState[0], setDone = doneState[1];
    var questionsState = useState(function () { return prepareQuestions(props.questions); });
    var questions = questionsState[0], setQuestions = questionsState[1];

    function restart() {
      setQuestions(prepareQuestions(props.questions));
      setIdx(0); setSelected(null); setScore(0); setDone(false); scrollTop();
      if (props.onRestart) props.onRestart();
    }

    if (done) {
      var pct = Math.round(score / questions.length * 100);
      var verdict = "Результат этой попытки";
      var band = pct >= 80 ? "var(--green)" : pct >= 55 ? "var(--amber)" : "var(--red)";
      return h("div", null,
        !props.hideBack ? h("button", { className: "quiz-back", onClick: props.onBack }, props.backLabel || "← Выбрать другой тест") : null,
        h("div", { className: "card fade-in" },
          h("div", { className: "kicker" }, quizLabels[props.kind] || "ТЕСТ"),
          h("div", { className: "result-score" }, score, h("span", null, "/" + questions.length)),
          h("div", { className: "result-bar" }, h("div", { style: { width: pct + "%", background: band } })),
          h("div", { className: "verdict", style: { color: band } }, verdict + " · " + pct + "%"),
          h("p", { className: "notes" }, "Балл отражает выбор ответов, а не доказывает освоение темы. Объясни причину решения без вариантов и разбери самостоятельную задачу с изменёнными условиями. Ошибки подскажут, к каким разделам вернуться."),
          h("button", { className: "primary wide", onClick: restart }, "Пройти заново")));
    }

    var current = questions[idx];
    var parsed = splitQuestion(current.q);
    var locked = selected !== null;
    return h("div", null,
      !props.hideBack ? h("button", { className: "quiz-back", onClick: props.onBack }, props.backLabel || "← Выбрать другой тест") : null,
      h("div", { className: "card fade-in", key: idx },
        h("div", { className: "quiz-top" },
          h("span", { className: "level-tag level-" + current.level }, levels[current.level] || current.level),
          h("span", { className: "counter" }, (idx + 1) + " / " + questions.length)),
        h("div", { className: "quiz-progress" }, h("div", { style: { width: ((idx + 1) / questions.length * 100) + "%" } })),
        h("h2", { className: "question" }, parsed.stem),
        parsed.code ? h("pre", { className: "question-code" }, h("code", null, parsed.code)) : null,
        h("div", { className: "options" }, current.options.map(function (option, optionIndex) {
          var className = "option";
          if (locked) {
            if (optionIndex === current.answer) className += " correct";
            else if (optionIndex === selected) className += " wrong";
            else className += " dim";
          }
          return h("button", {
            className: className,
            key: optionIndex,
            disabled: locked,
            onClick: function () {
              setSelected(optionIndex);
              if (optionIndex === current.answer) setScore(score + 1);
            }
          }, h("span", { className: "option-mark" }, String.fromCharCode(65 + optionIndex)), h("span", { className: "option-text" }, option));
        })),
        locked ? h("div", { className: "explanation" },
          h("div", { className: "explanation-label" + (selected === current.answer ? " correct" : "") }, selected === current.answer ? "Верно" : "Разбор"),
          h("p", null, current.why),
          current.theoryRefs && current.theoryRefs.length ? h("aside", { className: "quiz-theory-refs", "aria-label": "Объяснение в теории" },
            h("div", { className: "quiz-theory-label" }, "Повторить правило · откроется в новой вкладке"),
            h("ul", null, current.theoryRefs.map(function (id) {
              var section = theory.find(function (item) { return item.id === id; });
              if (!section) return null;
              var module = substations.find(function (item) { return item.id === section.substation; });
              return h("li", { key: id }, h("a", {
                href: "#section=" + encodeURIComponent(id),
                target: "_blank",
                rel: "noopener noreferrer"
              }, (module ? module.label + " · " : "") + section.title));
            }))) : null,
          h("button", { className: "primary wide", onClick: function () {
            if (idx + 1 === questions.length) {
              props.onSave(score, questions.length);
              setDone(true);
            } else {
              setIdx(idx + 1);
              setSelected(null);
              scrollTop();
            }
          } }, idx + 1 === questions.length ? "Показать результат" : "Следующий вопрос →")) : null));
  }

  function QuizArea(props) {
    var selectedState = useState(null);
    var selected = selectedState[0], setSelected = selectedState[1];
    if (!selected) return h(QuizPicker, { quizzes: props.quizzes, results: props.results, final: props.final, onChoose: setSelected });
    return h(Quiz, {
      key: selected,
      kind: selected,
      questions: props.quizzes[selected],
      onBack: function () { setSelected(null); scrollTop(); },
      onSave: function (score, total) { props.saveResult(selected, score, total); }
    });
  }

  function Training(props) {
    var settingsState = useState(function () { return trainingSettings(new URLSearchParams(window.location.hash.slice(1)), props.modules); });
    var settings = settingsState[0], setSettings = settingsState[1];
    var finishedState = useState(false), finished = finishedState[0], setFinished = finishedState[1];
    React.useEffect(function () {
      function followTrainingHash() {
        var params = new URLSearchParams(window.location.hash.slice(1));
        if (params.get("view") !== "training") return;
        setSettings(trainingSettings(params, props.modules));
        setFinished(false);
      }
      window.addEventListener("hashchange", followTrainingHash);
      window.addEventListener("popstate", followTrainingHash);
      return function () {
        window.removeEventListener("hashchange", followTrainingHash);
        window.removeEventListener("popstate", followTrainingHash);
      };
    }, [props.modules]);
    function choose(changes) {
      var next = Object.assign({}, settings, { batch: null }, changes);
      setSettings(next); setFinished(false);
      try { history.replaceState(null, "", trainingHash(next)); } catch (_) {}
      scrollTop();
    }
    var entries = trainingEntries(props.bank, settings.module, settings.kind);
    var batches = trainingBatches(entries, settings.size);
    var batch = settings.batch === null ? null : batches[settings.batch];
    var module = props.modules.find(function (item) { return item.id === settings.module; });
    var kindLabel = settings.kind === "basic" ? "Базовые" : settings.kind === "advanced" ? "Углублённые" : "Базовые и углублённые";
    if (batch) {
      return h("section", { className: "station-training" },
        h("h2", null, "Дополнительная тренировка"),
        h("p", { className: "notes training-scope" }, (module ? module.label + " · " + module.title : "Вся станция") + " · " + kindLabel),
        h("div", { className: "training-attempt-heading" },
          h("strong", null, "Набор " + (settings.batch + 1) + " из " + batches.length),
          h("span", null, "Вопросы " + (settings.batch * settings.size + 1) + "–" + Math.min((settings.batch + 1) * settings.size, entries.length) + " из " + entries.length)),
        h(Quiz, { key: trainingResultKey(batch), kind: "training", questions: batch.map(function (entry) { return entry.question; }),
          backLabel: "← К выбору набора", onBack: function () { choose({ batch: null }); },
          onRestart: function () { setFinished(false); },
          onSave: function (score, total) { props.onSave(trainingResultKey(batch), score, total); setFinished(true); } }),
        finished ? h("details", { className: "training-review" }, h("summary", null, "Разборы вопросов этого набора"), batch.map(function (entry, index) {
          var question = entry.question, parsed = splitQuestion(question.q);
          return h("article", { className: "training-review-item", key: entry.id },
            h("h3", null, (index + 1) + ". " + parsed.stem),
            parsed.code ? h("pre", { className: "question-code" }, h("code", null, parsed.code)) : null,
            h("p", { className: "training-review-answer" }, h("strong", null, "Верный ответ: "), question.options[question.answer]),
            h("p", null, question.why),
            h("ul", null, (question.theoryRefs || []).map(function (id) {
              var section = theory.find(function (item) { return item.id === id; });
              return section ? h("li", { key: id }, h("a", { href: "#section=" + encodeURIComponent(id), target: "_blank", rel: "noopener noreferrer" }, section.title, " ↗")) : null;
            })));
        })) : null,
        finished ? h("div", { className: "training-next section-actions" },
          settings.batch + 1 < batches.length ? h("button", { className: "primary", onClick: function () { choose({ batch: settings.batch + 1 }); } }, "Следующий набор →") : h("p", { className: "notes" }, "Это последний набор в выбранной подборке."),
          h("button", { className: "secondary", onClick: function () { choose({ batch: null }); } }, "Выбрать другую подборку")) : null);
    }
    return h("section", { className: "station-training" },
      h("div", { className: "kicker" }, "В СВОЁМ ТЕМПЕ"),
      h("h2", null, "Дополнительная тренировка"),
      h("p", { className: "section-lead" }, "Все базовые и углублённые вопросы станции — небольшими наборами. Выбери подглаву или повтори станцию целиком."),
      h("p", { className: "notes" }, "Это необязательная практика: её результаты сохраняются отдельно и не меняют балл итогового теста или отметки изученных разделов. Интервью-вопросы остаются в отдельном тренажёре."),
      h("div", { className: "training-filters", role: "group", "aria-label": "Подборка вопросов" },
        h("label", null, h("span", null, "Что повторить"), h("select", { value: settings.module, onChange: function (event) { choose({ module: event.target.value }); } },
          h("option", { value: "" }, "Вся станция"), props.modules.map(function (item) { return h("option", { key: item.id, value: item.id }, item.label + " · " + item.title); }))),
        h("label", null, h("span", null, "Вопросы"), h("select", { value: settings.kind, onChange: function (event) { choose({ kind: event.target.value }); } },
          h("option", { value: "all" }, "Базовые и углублённые"), h("option", { value: "basic" }, "Только базовые"), h("option", { value: "advanced" }, "Только углублённые"))),
        h("label", null, h("span", null, "Размер набора"), h("select", { value: settings.size, onChange: function (event) { choose({ size: Number(event.target.value) }); } },
          [5, 10, 15].map(function (size) { return h("option", { key: size, value: size }, "До " + size + " вопросов"); })))),
      h("p", { className: "training-summary", role: "status" }, entries.length ? "Вопросов в подборке: " + entries.length + " · Наборов: " + batches.length : "В этой подборке пока нет вопросов. Выбери другую подглаву или тип вопросов."),
      settings.batch !== null ? h("p", { className: "notes" }, "Такого набора в выбранной подборке нет. Выбери один из доступных ниже.") : null,
      batches.length ? h("div", { className: "training-batches", role: "group", "aria-label": "Наборы вопросов" }, batches.map(function (items, index) {
        var result = props.store[trainingResultKey(items)];
        return h("button", { key: trainingResultKey(items), className: "training-batch" + (result ? " is-attempted" : ""), onClick: function () { choose({ batch: index }); } },
          h("span", { className: "training-batch-number" }, "Набор " + (index + 1)),
          h("strong", null, "Вопросы " + (index * settings.size + 1) + "–" + Math.min((index + 1) * settings.size, entries.length)),
          h("span", { className: "training-batch-result" }, result ? "Последняя попытка: " + scoreText(result) : "Ещё не пройден"),
          h("span", { className: "training-batch-arrow", "aria-hidden": true }, "→"));
      })) : null,
      h("p", { className: "notes training-order" }, "Наборы последовательные, без случайного отбора: сначала базовые вопросы, затем углублённые. Поэтому можно дойти до каждого вопроса. При повторе меняется только порядок вариантов ответа; после выбора доступны объяснение и ссылки на теорию."));
  }

  function Tasks(props) {
    var activeState = useState(0);
    var active = activeState[0], setActive = activeState[1];
    var hintsState = useState(0);
    var shownHints = hintsState[0], setShownHints = hintsState[1];
    var solutionState = useState(false);
    var solutionShown = solutionState[0], setSolutionShown = solutionState[1];
    var checksState = useState({});
    var checked = checksState[0], setChecked = checksState[1];
    var taskItems = props.tasks;
    var task = taskItems[active];
    var currentModuleIndex = substations.findIndex(function (item) { return item.id === task.substation; });
    var laterModules = substations.filter(function (module, index) {
      return index > currentModuleIndex && task.theoryRefs.some(function (id) {
        return theory.some(function (section) { return section.id === id && section.substation === module.id; });
      });
    });

    function openTask(index) {
      setActive(index); setShownHints(0); setSolutionShown(false); setChecked({}); scrollTop();
    }

    return h("div", null,
      h("div", { className: "task-nav" }, taskItems.map(function (item, index) {
        return h("button", { className: "pill" + (index === active ? " active" : ""), key: index, onClick: function () { openTask(index); } }, (index + 1) + ". " + item.title);
      })),
      h("article", { className: "card fade-in", key: active },
        h("span", { className: "task-level" }, task.level),
        h("h2", { className: "task-title" }, task.title),
        laterModules.length ? h("p", { className: "task-revisit" },
          "Возвратное задание: для полного разбора сначала прочитай ",
          laterModules.map(function (module) { return module.label + " · " + module.title; }).join("; "),
          ". Затем вернись сюда; это не проверка знаний только текущей подстанции.") : null,
        h("p", { className: "task-brief" }, task.brief),
        task.code ? h("pre", { className: "question-code" }, h("code", null, task.code)) : null,
        h("details", { className: "task-preparation quiz-theory-refs" },
          h("summary", null, "Что прочитать перед заданием"),
          h("p", null, "Здесь разобраны правила и примеры, на которые опирается задание. Ссылки откроются в новой вкладке — условие останется перед тобой."),
          h("ul", null, task.theoryRefs.map(function (id) {
            var section = theory.find(function (item) { return item.id === id; });
            var module = substations.find(function (item) { return item.id === section.substation; });
            return h("li", { key: id }, h("a", {
              href: "#section=" + encodeURIComponent(id), target: "_blank", rel: "noopener noreferrer"
            }, (module ? module.label + " · " : "") + section.title));
          }))),
        h("div", { className: "try-note" }, "Сначала попробуй решить без подсказок. Открывай их по одной, если застрял."),
        task.checks ? h("div", { className: "self-check" },
          h("div", { className: "self-check-title" }, "ЧЕК-ЛИСТ ОТВЕТА"),
          task.checks.map(function (item, index) {
            return h("button", {
              className: "check-item" + (checked[index] ? " checked" : ""),
              key: index,
              "aria-pressed": !!checked[index],
              onClick: function () {
                var next = Object.assign({}, checked);
                next[index] = !next[index];
                setChecked(next);
              }
            }, h("span", { className: "check-mark" }, checked[index] ? "✓" : ""), h("span", null, item));
          })) : null,
        shownHints ? h("div", { className: "hints" }, task.hints.slice(0, shownHints).map(function (hint, index) {
          return h("div", { className: "hint", key: index }, h("span", { className: "hint-number" }, index + 1), h("span", { className: "hint-text" }, hint));
        })) : null,
        shownHints < task.hints.length ? h("button", { className: "hint-button", onClick: function () { setShownHints(shownHints + 1); } }, "Показать подсказку " + (shownHints + 1)) : null,
        h("div", { style: { height: "12px" } }),
        !solutionShown ? h("button", { className: "solution-button", onClick: function () { setSolutionShown(true); } }, "Показать решение") : h("div", null,
          h("div", { className: "solution-label" }, "РЕШЕНИЕ"),
          task.solutionFormat === "code"
            ? h("pre", { className: "solution-code" }, h("code", null, task.solution))
            : h("div", { className: "task-solution-text" }, task.solution.split(/\n\s*\n/).map(function (paragraph, index) {
                return h("p", { key: index }, paragraph);
              })),
          h("div", { className: "notes-label" }, "ПОЧЕМУ ТАК"),
          h("p", { className: "notes" }, task.notes),
          h("button", { className: "ghost", onClick: function () { setSolutionShown(false); } }, "Скрыть решение"))));
  }

  function App() {
    var textSizeState = useState(function () {
      try { return localStorage.getItem("cpp_course_text_size_v1") === "large"; } catch (_) { return false; }
    });
    function setLargeText(value) {
      textSizeState[1](value);
      try { localStorage.setItem("cpp_course_text_size_v1", value ? "large" : "normal"); } catch (_) {}
    }
    var routeModeState = useState(function () { return loadStore().readingRoute !== false; });
    var routeMode = routeModeState[0], setRouteMode = routeModeState[1];
    var sectionState = useState(requestedSection ? requestedSection.id : "");
    var selectedSectionId = sectionState[0], setSelectedSectionId = sectionState[1];
    var tabState = useState(requestedView);
    var tab = tabState[0], setTab = tabState[1];
    var storeState = useState(loadStore);
    var store = storeState[0], setStore = storeState[1];
    var substationState = useState(function () {
      if (requestedSection) return requestedSection.substation || "";
      if (substations.some(function (item) { return item.id === requestedModule; })) return requestedModule;
      var saved = loadStore().activeSubstation;
      return substations.some(function (item) { return item.id === saved; })
        ? saved : (substations[0] ? substations[0].id : "");
    });
    var activeSubstationId = substationState[0], setActiveSubstationId = substationState[1];
    // Links from the embedded trainer navigate this existing document by hash.
    // React state must follow that navigation as well as initial page loading.
    React.useEffect(function () {
      function followHash() {
        var params = new URLSearchParams(window.location.hash.slice(1));
        var section = theory.find(function (item) { return item.id === params.get("section"); });
        if (!section) {
          var view = params.get("view");
          if (["checkpoint", "final", "quiz", "interview", "tasks", "analysis", "training"].indexOf(view) < 0) return;
          setTab(view);
          var moduleId = params.get("module");
          if (view === "checkpoint" && substations.some(function (item) { return item.id === moduleId; })) setActiveSubstationId(moduleId);
          scrollTop();
          return;
        }
        setTab("theory");
        setSelectedSectionId(section.id);
        setActiveSubstationId(section.substation || "");
        setStore(function (previous) {
          var next = Object.assign({}, previous, { activeSubstation: section.substation || "" });
          persist(next);
          return next;
        });
        scrollTop();
      }
      window.addEventListener("hashchange", followHash);
      window.addEventListener("popstate", followHash);
      return function () {
        window.removeEventListener("hashchange", followHash);
        window.removeEventListener("popstate", followHash);
      };
    }, []);
    var hasSubstations = substations.length > 0;
    var activeSubstation = substations.find(function (item) { return item.id === activeSubstationId; });
    var selectedWorkbook = theory.find(function (item) { return item.id === selectedSectionId && isWorkbook(item); });
    var activeTheory = selectedWorkbook ? [selectedWorkbook] : theory.filter(function (item) { return (!hasSubstations || item.substation === activeSubstationId) && !isWorkbook(item); });
    if (routeMode && data.readingOrder && !selectedWorkbook) activeTheory.sort(function (a, b) { return data.readingOrder.indexOf(a.id) - data.readingOrder.indexOf(b.id); });
    var activeTasks = tasks.filter(isPracticeTask);
    var analysisTasks = tasks.filter(function (task) { return !isPracticeTask(task); });
    var priorityRefs = assessmentPriorityRefs(meta.id);
    var activeQuizzes = { basic: finalQuestions(quizzes, substations, 25, meta.number <= 4, priorityRefs, assessmentFinalBudgets(meta.id)), interview: quizzes.interview || [] };
    var checkpointQuestions = chapterQuestions(quizzes, activeSubstationId, assessmentCheckpointRefs(meta.id));
    var workedSections = theory.filter(function (section) { return /(?:-final-workbook|clock-worked-example)$/.test(section.id); });
    var doneSections = theory.filter(function (item) { return store["sec:" + item.id]; }).length;
    var doneActiveSections = activeTheory.filter(function (item) { return store["sec:" + item.id]; }).length;

    function quizStoreKey(kind) {
      if (["station3", "station5", "station5-linux", "station6", "station9-sql"].indexOf(meta.id) >= 0) return "station-final:systems-depth-20261025:v1:" + kind;
      if (["station7", "station8", "station9", "station10"].indexOf(meta.id) >= 0) return "station-final:architecture-20261025:v1:" + kind;
      if (meta.id === "station7-netlab") return "station-final:netlab-20261021:v1:" + kind;
      if (meta.id === "station7-traffic") return "station-final:traffic-20261026:v1:" + kind;
      if (meta.number === 7 && (kind === "basic" || kind === "interview")) return "station-final:network-foundation-20261021:v1:" + kind;
      if (kind === "interview" && [3,6,9].indexOf(meta.number) >= 0) return "station-final:audit-20261015:v1:" + kind;
      if (meta.number === 9) return "station-final:database-split:v1:" + kind;
      if (kind === "interview" && [1,5,6,7,10].indexOf(meta.number) >= 0) return "station-final:interview-gaps:v1:" + kind;
      if (meta.number <= 4 && kind === "basic") return "station-final:coverage:v1:" + kind;
      return (kind === "basic" ? "station-final:v3:" : "station-final:v2:") + kind;
    }

    var quizResults = {
      basic: store[quizStoreKey("basic")],
      advanced: store[quizStoreKey("advanced")],
      interview: store[quizStoreKey("interview")]
    };

    function updateStore(changes) {
      var next = Object.assign({}, store, changes);
      setStore(next);
      persist(next);
    }

    function openPage(view, moduleId) {
      var id = moduleId || activeSubstationId;
      setTab(view);
      if (moduleId) { setSelectedSectionId(""); setActiveSubstationId(moduleId); updateStore({ activeSubstation: moduleId }); }
      try { history.replaceState(null, "", "#view=" + view + (view === "checkpoint" ? "&module=" + encodeURIComponent(id) : "")); } catch (_) {}
      scrollTop();
    }
    function chooseSubstation(id) {
      var first = theory.find(function (item) { return item.substation === id && !isWorkbook(item); });
      if (first) navigateSection(first.id);
    }
    function continueChapter() {
      var index = substations.findIndex(function (item) { return item.id === activeSubstationId; });
      if (index + 1 < substations.length) chooseSubstation(substations[index + 1].id);
      else openPage("final");
    }

    function navigateSection(id) {
      var section = theory.find(function (item) { return item.id === id; });
      if (!section) return;
      setTab("theory");
      try { history.replaceState(null, "", "#section=" + encodeURIComponent(id)); } catch (_) {}
      setActiveSubstationId(section.substation || "");
      setSelectedSectionId(section.id);
      updateStore({ activeSubstation: section.substation || "" });
      scrollTop();
    }

    return h("main", { className: "page" + (hasSubstations ? " page-wide" : "") + (textSizeState[0] ? " reading-large" : "") },
      h("header", { className: "hero" },
        h("div", { className: "logo" }, meta.logo),
        h("h1", null, meta.title),
        h("p", { className: "hero-sub" }, meta.subtitle),
        h("div", { className: "reading-settings", role: "group", "aria-label": "Размер текста" },
          h("span", null, "Текст"),
          h("button", { type: "button", "aria-pressed": !textSizeState[0], onClick: function () { setLargeText(false); } }, "Обычный"),
          h("button", { type: "button", "aria-pressed": textSizeState[0], onClick: function () { setLargeText(true); } }, "Крупнее")),
        location.protocol === "file:" ? h("div", { className: "file-warning" }, "Страница открыта как файл. Для надёжной загрузки React и сохранения прогресса запусти roadmap через локальный HTTP-сервер.") : null,
        h("p", { className: "reading-progress" }, "Изученные разделы: " + doneSections + " / " + theory.length)),
      hasSubstations ? h(SubstationNav, { items: substations, active: activeSubstationId, selected: selectedSectionId, view: tab, store: store, onChoose: chooseSubstation, onNavigate: navigateSection, onCheckpoint: function (id) { openPage("checkpoint", id); }, onPage: openPage }) : null,
      (tab === "quiz" || tab === "interview" || tab === "tasks" || tab === "training" || (tab === "theory" && selectedWorkbook)) ? h("button", { className: "ghost", onClick: function () { openPage("final"); } }, "← Завершение станции") : null,
      tab === "theory" && data.readingOrder ? h("div", { className: "section-actions", "aria-label": "Порядок чтения" },
        h("button", { className: "secondary reading-mode", "aria-pressed": routeMode, onClick: function () { setRouteMode(true); updateStore({ readingRoute: true }); } }, "Первое чтение"),
        h("button", { className: "secondary reading-mode", "aria-pressed": !routeMode, onClick: function () { setRouteMode(false); updateStore({ readingRoute: false }); } }, "По темам")) : null,
      tab === "theory" ? h(Theory, { key: (activeSubstationId || "all") + ":" + selectedSectionId, sections: activeTheory, initialSectionId: selectedSectionId, readingOrder: routeMode ? data.readingOrder : null, onNavigate: navigateSection, onComplete: function () { if (selectedWorkbook) openPage("quiz"); else openPage("checkpoint", activeSubstationId); }, store: store, toggleSection: function (id) { var change = {}; change["sec:" + id] = !store["sec:" + id]; updateStore(change); } }) : null,
      (tab === "quiz" || tab === "interview") ? h("section", null,
        h("h2", null, tab === "quiz" ? "Итоговый тест по станции" : "Интервью-тренажёр"),
        tab === "quiz" && analysisTasks.length ? h("div", { className: "assessment-extra" }, h("p", null, "Дополнительно — вопросы с самостоятельным ответом и разбором: " + analysisTasks.length + ". Попробуй ответить самостоятельно, потом открой подсказки и решение."), h("button", { className: "secondary", onClick: function () { openPage("analysis"); } }, "Открыть вопросы с разбором →")) : null,
        h(Quiz, { key: tab, hideBack: true, kind: tab === "quiz" ? "basic" : "interview", questions: tab === "quiz" ? activeQuizzes.basic : activeQuizzes.interview, onSave: function (score, total) {
          var change = {}; change[quizStoreKey(tab === "quiz" ? "basic" : "interview")] = { score: score, total: total, at: new Date().toISOString() }; updateStore(change);
        } }),
        h("button", { className: "secondary", onClick: function () { openPage(tab === "quiz" ? "interview" : "tasks"); } }, tab === "quiz" ? "Далее: интервью-тренажёр →" : "Далее: практика →")) : null,
      tab === "checkpoint" ? h("section", { className: "station-checkpoint" },
        h("h2", null, "Закрепление: " + (activeSubstation ? activeSubstation.title : meta.title)),
        h("p", { className: "notes" }, "Короткая проверка текущей темы. Общий тест и интервью находятся в завершении станции."),
        checkpointQuestions.length ? h(Quiz, { key: "checkpoint:" + activeSubstationId, backLabel: "← Вернуться к подглаве", kind: "basic", questions: checkpointQuestions,
          onBack: function () { var last = activeTheory[activeTheory.length - 1]; if (last) navigateSection(last.id); }, onSave: function (score, total) { var change = {}; change["checkpoint:v2:" + activeSubstationId] = { score: score, total: total }; updateStore(change); } }) : h("p", null, "Для этой темы короткая проверка ещё готовится."), h("div", { className: "section-actions" }, h("button", { className: "secondary", onClick: continueChapter }, "Далее по учебнику →"))) : null,
      tab === "final" ? h("section", { className: "station-finale" },
        h("p", { className: "kicker" }, "ЗАВЕРШЕНИЕ СТАНЦИИ " + (meta.id === "station5-linux" ? "5Б" : meta.id === "station7-netlab" ? "7Б" : meta.id === "station7-traffic" ? "7В" : meta.number === 9 ? (meta.id === "station9-sql" ? "9A" : "9B") : meta.number)),
        h("h2", null, "Собираем знания вместе"),
        h("p", { className: "section-lead" }, "Сначала проследи решение целой задачи, затем проверь знания всей станции и переходи к самостоятельной работе."),
        h("div", { className: "finale-grid" },
          h("div", { className: "finale-item" }, h("span", { className: "kicker" }, "01 · РАЗБОР"), h("h3", null, "Задача с объяснением"), workedSections.map(function (section) { return h("button", { className: "secondary", key: section.id, onClick: function () { navigateSection(section.id); } }, section.title); })),
          h("div", { className: "finale-item" }, h("span", { className: "kicker" }, "02 · ПРОВЕРКА"), h("h3", null, "Итоговый тест"), h("p", null, activeQuizzes.basic.length + " вопросов по темам всей станции с объяснением ответов."), h("button", { className: "secondary", onClick: function () { openPage("quiz"); } }, "Открыть итоговый тест →"),
            h("div", { className: "training-entry" }, h("p", null, "Хочешь ещё потренироваться? Базовые и углублённые вопросы (" + trainingEntries(quizzes).length + ") доступны по подглавам, небольшими наборами."), h("button", { className: "secondary", onClick: function () { openPage("training"); } }, "Дополнительная тренировка →"))),
          h("div", { className: "finale-item" }, h("span", { className: "kicker" }, "03 · СОБЕСЕДОВАНИЕ"), h("h3", null, "Интервью-тренажёр"), h("p", null, "Вопросов для подготовки к собеседованию: " + activeQuizzes.interview.length + ". Прежде чем выбирать ответ, попробуй объяснить решение вслух."), h("button", { className: "secondary", onClick: function () { openPage("interview"); } }, "Открыть интервью-тренажёр →")),
          h("div", { className: "finale-item" }, h("span", { className: "kicker" }, "04 · ПРИМЕНЕНИЕ"), h("h3", null, "Практика"), h("p", null, "Задачи из открытых курсов, лабораторные и LeetCode по теме станции. Вопросы на предсказание вывода перенесены к тестам."), h("button", { className: "secondary", onClick: function () { openPage("tasks"); } }, "Перейти к заданиям →")))) : null,
      tab === "analysis" ? h("section", null, h("h2", null, "Вопросы с разбором"), h("p", { className: "notes" }, "Ответь своими словами до открытия подсказок. Эти вопросы не входят в оценку итогового теста на 25 вопросов."), h("button", { className: "ghost", onClick: function () { openPage("quiz"); } }, "← К итоговому тесту"), analysisTasks.length ? h(Tasks, { key: "analysis", tasks: analysisTasks }) : null) : null,
      tab === "training" ? h(Training, { bank: quizzes, modules: substations, store: store, onSave: function (key, score, total) {
        if (!key || key.indexOf("station-training:v1:") !== 0 || !Number.isInteger(score) || !Number.isInteger(total) || total < 1 || score < 0 || score > total) return;
        var change = {}; change[key] = { score: score, total: total, at: new Date().toISOString() }; updateStore(change);
      } }) : null,
      tab === "tasks" ? h("section", null, h(PracticeLinks), activeTasks.length ? h("div", null, h("h3", null, "Задачи учебника"), h(Tasks, { key: "station-practice", tasks: activeTasks })) : null) : null,
      h("div", { className: "footer-row" }, h("button", { className: "reset", onClick: function () { if (confirm("Сбросить прогресс этой станции?")) { var cleared = meta.id === "station9-sql" ? { migratedFromDatabases: true } : {}; try { localStorage.setItem(meta.storeKey, JSON.stringify(cleared)); } catch (_) {} setStore(cleared); } } }, "Сбросить прогресс")),
      h("footer", null, h("a", { href: "cpp_backend_roadmap.html" }, "← К программе курса"), " · ", h("a", { href: "sources.html#" + meta.id }, "Источники станции")));
  }

  ReactDOM.createRoot(root).render(h(App));
}());
