/* Prepared teaching experiments. No arbitrary code execution or network I/O. */
(function (global) {
  "use strict";
  const copy = value => JSON.parse(JSON.stringify(value));
  function trace(type, code, language, initial, program) {
    const result = {type, code:code.split("\n"), language, program:program || null, steps:[]};
    result.add = function(line,title,text,rule,state,note) {
      result.steps.push({line,title,text,rule,state:copy(state || initial),note:note || ""});
    };
    return result;
  }
  const ownerProgram = `#include <memory>\n#include <iostream>\nstruct Item { ~Item() { std::cout << "destroy Item\\n"; } };\nint main() {\n    auto a = std::make_shared<Item>();\n    auto b = a;\n    std::weak_ptr<Item> w = a;\n    a.reset();\n    auto held = w.lock();\n    b.reset();\n    std::cout << w.expired() << '\\n';\n    held.reset();\n    std::cout << w.expired() << '\\n';\n    w.reset();\n}\n`;
  function ownership(mode) {
    if (mode === "unique") {
      const code = `auto a = std::make_unique<Item>();\nItem* observer = a.get();\nauto b = std::move(a);\n// a == nullptr; observer still points to Item\nb.reset();\n// observer must not be dereferenced`;
      const program = `#include <memory>\n#include <iostream>\n#include <utility>\nstruct Item { ~Item() { std::cout << "destroy Item\\n"; } };\nint main() {\n${code}\nstd::cout << bool(a) << ' ' << bool(b) << '\\n';\n}\n`;
      const s = {owners:[],declared:[],created:false,alive:false,control:false,strong:0,weak:0,observer:false,observerValid:false};
      const t = trace("ownership",code,"C++20 · main, тип Item показан в полной программе",s,program);
      t.add(0,"До создания владельца","Переменная unique_ptr и управляемый Item — разные объекты. Начнём с одного владельца.","На схеме показаны логические связи, а не адреса и размещение полей указателя.",s);
      Object.assign(s,{owners:["a"],declared:["a"],created:true,alive:true,strong:1});t.add(0,"a владеет Item","make_unique создала Item и вернула его единственного владельца a.","В этой модели выделение памяти и создание Item успешны.",s,"Создан один Item; a владеет им.");
      Object.assign(s,{observer:true,observerValid:true});t.add(1,"observer только наблюдает","get возвращает адрес. Сырой указатель observer не обязан освобождать Item и не удерживает его живым.","Наблюдение не добавляет владельца.",s,"Владельцев по-прежнему один.");
      s.owners=["b"];s.declared.push("b");t.add(2,"Владение передано b","После перемещения a пуста. Item не перемещался в другое место и не создавался заново: владельцем того же объекта стала b.","std::move само по себе — преобразование категории выражения; передача здесь выполняется конструктором unique_ptr.",s,"a пуста; b владеет прежним Item; observer пока пригоден.");
      Object.assign(s,{owners:[],alive:false,strong:0,observerValid:false});t.add(4,"Последний владелец освобождает ресурс","reset у b вызывает удаление Item. observer не обнуляется автоматически, но больше не даёт права обращаться к объекту.","В программе недействительный observer не разыменовывается.",s,"Item уничтожен. a и b пусты; observer недействителен.");
      return t;
    }
    if (mode === "cycle" || mode === "weak-cycle") {
      const weak = mode === "weak-cycle";
      const code = `struct Node {\n  std::shared_ptr<Node> next;\n  ${weak?"std::weak_ptr<Node>":"std::shared_ptr<Node>"} back;\n};\nauto a = std::make_shared<Node>();\nauto b = std::make_shared<Node>();\na->next = b;\nb->back = a;\na.reset();\nb.reset();`;
      const s={cycle:true,created:false,weakBack:weak,externalA:false,externalB:false,linked:false,aliveA:false,aliveB:false,countA:0,countB:0};
      const t=trace("ownership",code,"C++20 · фрагмент",s);
      t.add(4,"Два узла и две внешние ссылки","Создадим A и B. Затем свяжем их в обоих направлениях.","Цикл ссылок и цикл сильного владения — не одно и то же.",s);
      Object.assign(s,{created:true,externalA:true,externalB:true,aliveA:true,aliveB:true,countA:1,countB:1});t.add(5,"Пока каждым владеет одна переменная","a удерживает A, b удерживает B. У каждого по одному сильному владельцу.","Счётчики относятся к отдельным объектам.",s,"A: 1, B: 1 сильный владелец.");
      Object.assign(s,{linked:true,countA:weak?1:2,countB:2});t.add(7,"Добавляем связи между узлами",weak?"A.next удерживает B, но B.back лишь наблюдает A. Слабая обратная связь не увеличивает сильный счётчик A.":"A.next удерживает B, а B.back удерживает A. Теперь каждый узел имеет ещё одного сильного владельца внутри другого узла.","На схеме сплошная стрелка — сильное владение, пунктирная — слабое наблюдение.",s,weak?"A: 1, B: 2. Обратная связь слабая.":"A: 2, B: 2. Обе внутренние связи сильные.");
      s.externalA=false;s.countA--;if(weak){s.aliveA=false;s.countA=0;s.countB--;}
      t.add(8,"Убираем внешнюю ссылку a",weak?"Сильных владельцев A больше нет: A уничтожается. Его поле next освобождает свою долю владения B; B остаётся жив благодаря b.":"A остаётся жив: им всё ещё владеет поле B.back. Его next тоже остаётся жив и продолжает удерживать B.","Уничтожение узла разрушает и его поля-владельцы.",s,weak?"A уничтожен; у B остался один сильный владелец.":"A: 1, B: 2. Удаление a не разорвало цикл.");
      s.externalB=false;s.countB--;if(weak){s.aliveB=false;s.countB=0;}t.add(9,"Убираем внешнюю ссылку b",weak?"Последний владелец B исчез. B уничтожается; слабая back не удерживала A. Оба узла освобождены.":"Оба узла остаются живы: внутренние сильные связи удерживают друг друга. Внешних владельцев уже нет, но счётчики не дошли до нуля.",weak?"Слабую связь выбирают по смыслу владения, а не добавляют случайно.":"shared_ptr не является сборщиком циклического мусора. Это намеренно показанная утечка, не корректное завершение владения.",s,weak?"Оба узла уничтожены.":"A: 1, B: 1. Цикл удерживает оба объекта.");
      return t;
    }
    const code=`auto a = std::make_shared<Item>();\nauto b = a;\nstd::weak_ptr<Item> w = a;\na.reset();\nauto held = w.lock();\nb.reset();\n// w.expired() == false\nheld.reset();\n// w.expired() == true\nw.reset();`;
    const s={owners:[],declared:[],created:false,weakDeclared:false,alive:false,control:false,strong:0,weak:0,observer:false,observerValid:false};
    const t=trace("ownership",code,"C++20 · main, Item в полной программе",s,ownerProgram);
    t.add(0,"Считаем связи, а не имена","Создадим один Item и несколько способов доступа к нему. Отдельно проследим время жизни объекта и управляющего блока.","Число weak на схеме — число явно созданных слабых ссылок, не внутренний счётчик реализации.",s);
    Object.assign(s,{owners:["a"],declared:["a"],created:true,alive:true,control:true,strong:1});t.add(0,"Первый сильный владелец","a владеет Item. Управляющий блок содержит служебные сведения о совместном владении.","В этой модели нет aliasing-конструктора: хранимый адрес соответствует Item.",s,"Сильных: 1. Item жив.");
    s.owners.push("b");s.declared.push("b");s.strong=2;t.add(1,"Копируется владелец","b разделяет владение тем же Item. Второй Item не создаётся.","Копирование shared_ptr и копирование Item — разные операции.",s,"Сильных: 2. Объект всё ещё один.");
    s.weak=1;s.weakDeclared=true;t.add(2,"Слабая ссылка не удерживает Item","w связана с той же группой владения. Число сильных владельцев осталось 2.","weak_ptr не даёт безопасного разыменования; сначала нужно получить владельца через lock.",s,"Сильных: 2, явных слабых: 1.");
    s.owners=["b"];s.strong=1;t.add(3,"a больше не владеет","a.reset уменьшила число сильных владельцев. b ещё удерживает Item живым.","reset одной ссылки не приказывает уничтожить объект независимо от остальных владельцев.",s,"Сильных: 1. Item жив.");
    s.owners.push("held");s.declared.push("held");s.strong=2;t.add(4,"Успешный lock создаёт сильного владельца","w.lock вернула shared_ptr held. Пока held существует, Item остаётся жив, даже если остальные владельцы исчезнут.","Проверка expired сама по себе не удерживала бы объект; здесь владение получено через lock.",s,"Сильных: 2. held удерживает Item.");
    s.owners=["held"];s.strong=1;t.add(5,"b освобождает свою долю","После b.reset последний сильный владелец — held. w.expired по-прежнему false.","Слабая ссылка не истекла, пока существует сильный владелец.",s,"Сильных: 1. Item жив.");
    Object.assign(s,{owners:[],strong:0,alive:false});t.add(7,"Исчез последний сильный владелец","held.reset уничтожает Item. w ещё существует, поэтому сведения, необходимые слабой ссылке, остаются доступны в управляющем блоке.","При make_shared память может оставаться общей с управляющим блоком, хотя время жизни Item уже закончилось.",s,"Item уничтожен; w.expired теперь true.");
    Object.assign(s,{weak:0,control:false});t.add(9,"Исчезла и последняя слабая ссылка","w.reset освободила последнюю явную слабую ссылку. Группа владения больше не нужна.","Различай конец жизни Item и освобождение управляющего блока.",s,"Ни живого Item, ни используемого управляющего блока не осталось.");
    return t;
  }

  function vector(mode) {
    const reserved=mode==="reserved",erase=mode==="erase";
    const code=erase?`std::vector<int> v{10, 20, 30};\nauto before = v.begin();\nauto at = v.begin() + 1;\nauto after = v.begin() + 2;\nauto next = v.erase(at);\n// before remains valid; at and after do not\n// next is the returned, valid iterator`:`std::vector<int> v;\nv.reserve(${reserved?4:2});\nv.push_back(10);\nv.push_back(20);\nint* p = &v[0];\nv.push_back(30);\n// Is p still valid? Check whether reallocation occurred.`;
    const s={values:erase?[10,20,30]:[],capacity:erase?3:reserved?4:2,buffer:"A",oldBuffer:null,pointer:"none",erased:false,mode};
    const t=trace("vector",code,"C++20 · фрагмент; конкретная ёмкость задана моделью",s);
    t.add(erase?0:1,"Сначала определяем условия","Начинаем после "+(erase?"инициализации vector тремя значениями":"успешного reserve")+". В модели буфер A имеет ёмкость "+s.capacity+". Ячейки показывают элементы и запас, а не точное число байтов.","reserve(N) гарантирует capacity ≥ N. Выбранная здесь ёмкость допустима, но не обязательна для каждой реализации.",s);
    if(erase){
      s.values=[10,20,30];s.pointer="all-valid";t.add(3,"Сохранили три итератора","before относится к 10, at — к 20, after — к 30. Все получены до удаления.","Итератор — не устойчивый логический идентификатор элемента.",s,"size = 3. Все три итератора пока пригодны.");
      s.values=[10,30];s.erased=true;s.pointer="at-after-invalid";t.add(4,"Удаляем средний элемент","erase сдвигает последующие значения. Итераторы и ссылки в точке удаления и после неё становятся недействительными; before остаётся пригоден.","Инвалидация возможна и без перераспределения памяти.",s,"size = 2. at и after недействительны; before пригоден.");
      t.add(6,"Используем результат erase","Новый итератор next возвращён самой операцией и указывает на следующий элемент 30. Старый at не становится разрешённым только потому, что по той же позиции теперь хранится 30.","После стирания продолжай обход возвращённым итератором, а не старым.",s,"next указывает на 30; старые at/after не используются.");
    }else{
      s.values=[10,20];t.add(3,"Два элемента занимают буфер","size равно 2. capacity показывает место для элементов без следующего перераспределения.","Резервные ячейки не являются уже существующими элементами vector.",s,"size = 2; capacity = "+s.capacity+" в этой модели.");
      s.pointer="valid";t.add(4,"p относится к первому элементу","Сохранили адрес v[0]. Пока буфер остаётся прежним и сам элемент не удалён, этот доступ пригоден.","Хранение p не запрещает контейнеру сменить буфер.",s,"p пригоден и относится к 10.");
      if(!reserved){s.oldBuffer="A";s.buffer="B";s.capacity=4;s.pointer="invalid";}s.values.push(30);
      t.add(5,reserved?"Есть запас — буфер не меняется":"Запаса нет — нужен новый буфер",reserved?"Для третьего элемента достаточно capacity=4. При вставке в конец без перераспределения указатель на прежний первый элемент сохраняет пригодность.":"Новый размер превышает прежнюю ёмкость. vector получает другой буфер, переносит значения и освобождает прежнее хранилище. Все старые указатели, ссылки и итераторы на элементы инвалидируются.",reserved?"Старый end() при push_back всё равно инвалидируется; p не был итератором конца.":"Новая ёмкость 4 — выбор модели, а не гарантированный коэффициент роста vector.",s,reserved?"p всё ещё пригоден; буфер A.":"p недействителен; данные теперь в буфере B.");
      t.add(6,"Проверяем право доступа",reserved?"p можно использовать для прежнего первого элемента. Наличие запаса помогло именно в показанном сценарии вставки в конец.":"Для доступа к 10 нужно заново получить адрес из текущего vector. Старый p не разыменовываем и не пытаемся угадать результат такого обращения.","reserve не защищает от всех видов инвалидации: сравни отдельный сценарий erase.",s);
    }
    return t;
  }

  function build(mode) {
    const changed={header:"types.hpp",source:"core.cpp",readme:"README.md"}[mode];
    const code=`// core.cpp                 // main.cpp\n#include "types.hpp"       #include "types.hpp"\n// implementation           // uses the interface\n\n# Build dependencies (conceptual, not CMake syntax):\ncore.o <- core.cpp, types.hpp\nmain.o <- main.cpp, types.hpp\napp    <- core.o, main.o\n\n# README.md is not an input of these build rules.`;
    const names=["types.hpp","core.cpp","main.cpp","core.o","main.o","app","README.md"];
    const s={changed,status:Object.fromEntries(names.map(n=>[n,"ready"]))};
    const t=trace("build",code,"Граф сборки · файлы этого учебного проекта",s);
    t.add(0,"Исходно сборка актуальна","Оба .cpp уже скомпилированы, app слинкована. Для этого опыта меняем только "+changed+".","Зависимости заголовка учитываются системой сборки; здесь они заданы явно.",s);
    s.status[changed]="changed";
    const objects=mode==="header"?["core.o","main.o"]:mode==="source"?["core.o"]:[];
    objects.forEach(o=>s.status[o]="dirty");if(objects.length)s.status.app="dirty";
    t.add(mode==="readme"?9:mode==="header"?1:0,"Распространяем изменение по зависимостям",objects.length?"Изменён входной файл. Объектные файлы, зависящие от него, устарели; app зависит от их будущего результата.":"README не является входом этих правил. Для данного изменения объектные файлы и app остаются актуальны.","Граф конкретного проекта важнее расширения изменённого файла: генератор мог бы сделать README входом другой цели.",s,objects.length?"Нужна компиляция: "+objects.join(", ")+"; затем линковка app.":"Компиляция и линковка не нужны.");
    for(const obj of objects){s.status[obj]="building";t.add(obj==="core.o"?5:6,"Компилируем "+obj,"Компилятор обрабатывает соответствующий .cpp вместе с включёнными заголовками. Другой независимый .cpp не становится частью той же единицы трансляции.","Это обычная раздельная сборка, без unity build и модулей.",s,"Выполняется компиляция "+obj);s.status[obj]="ready";t.add(obj==="core.o"?5:6,obj+" готов","Получен новый объектный файл. Пока app не перелинкована, запускаемый файл ещё прежний.","Успех отдельной компиляции не означает успех линковки.",s);}
    if(objects.length){s.status.app="building";t.add(7,"Линкуем app","Линкер собирает программу из актуальных core.o и main.o. Даже если main.o не пересоздавался, он участвует в линковке.","Неизменившийся объектный файл можно использовать повторно.",s);s.status.app="ready";}
    t.add(7,"Граф снова согласован",objects.length?"Сборка обновила нужные части. Запуск тестов — отдельное действие: актуальная app ещё не доказывает правильность её поведения.":"Исходники программы не изменялись. Обновление документации всё равно может иметь собственные проверки вне этого графа.","Граф не определяет безопасность ABI и не заменяет тесты.",s,"Все цели этого графа актуальны.");
    return t;
  }

  function concurrencyInitial() {
    return {value:0,locals:{A:null,B:null},pc:{A:0,B:0},lock:null,blocked:{A:false,B:false},mode:"separate",last:null};
  }
  function concurrencyStep(previous,who,mode) {
    const s=copy(previous),count=mode==="mutex"?5:mode==="rmw"?1:3;
    if(s.pc[who]>=count)return null;
    const other=who==="A"?"B":"A",n=s.pc[who];s.last=who;
    let title,text,rule,line;
    if(mode==="mutex"&&n===0){
      if(s.lock&&s.lock!==who){s.blocked[who]=true;return {line:2,title:"Поток "+who+" ждёт mutex",text:"Замок принадлежит потоку "+s.lock+". Поток "+who+" пока не может начать защищённое чтение.",rule:"Ожидающий поток не выполняет тело критической секции. Выбери шаг владельца замка.",state:s,note:who+": ожидание; counter = "+s.value};}
      s.lock=who;s.blocked[who]=false;title=who+" захватывает mutex";text="Вся последовательность чтения, расчёта и записи будет под одним замком.";rule="Одного замка только вокруг store было бы недостаточно.";line=2;
    }else if(mode==="mutex"&&n===4){s.lock=null;s.blocked[other]=false;title=who+" освобождает mutex";text="Защищённое изменение завершено. Теперь другой поток может взять замок и прочитать уже обновлённый counter.";rule="Разблокировка делает возможным следующий захват, но не выбирает планировщика за нас.";line=6;
    }else if(mode==="rmw") {const old=s.value;s.value++;s.locals[who]=old;title=who+": одно fetch_add";text="Атомарное read-modify-write увеличило counter с "+old+" до "+s.value+". Другая такая операция не вклинится между его чтением и записью.";rule="relaxed достаточно для самого счётчика; публикация других данных — отдельный протокол.";line=1;
    }else{
      const action=mode==="mutex"?n-1:n;
      if(action===0){s.locals[who]=s.value;title=who+" читает "+s.value;text="Значение counter скопировано в локальную переменную потока. Следующее изменение counter не обновит эту копию автоматически.";rule=mode==="mutex"?"Все обращения потоков к обычному int защищены одним и тем же mutex.":"load атомарен, но вся последовательность load → увеличение → store не стала одной операцией.";line=mode==="mutex"?3:1;}
      else if(action===1){s.locals[who]++;title=who+" увеличивает локальную копию";text="Локальное значение теперь "+s.locals[who]+". Общий counter пока равен "+s.value+".";rule="Локальный расчёт не меняет общую переменную.";line=mode==="mutex"?4:2;}
      else {s.value=s.locals[who];title=who+" записывает "+s.value;text=mode==="mutex"?"Запись сохраняет вычисленный результат. Другой участник не мог прочитать counter посередине этой критической секции.":"store сохраняет подготовленное значение. Если другой поток вычислил результат из того же старого значения, одно увеличение может быть потеряно.";rule=mode==="mutex"?"Один замок охватывает чтение, расчёт и запись.":"Все обращения к counter атомарны: это логическая гонка, не data race на обычном int.";line=mode==="mutex"?5:3;}
    }
    s.pc[who]++;
    return {line,title,text,rule,state:s,note:who+": counter = "+s.value+", локально = "+(s.locals[who]===null?"—":s.locals[who])};
  }
  function concurrency(mode) {
    const code=mode==="mutex"?`int counter = 0; std::mutex mutex;\n// Entire operation in EACH thread:\n{ std::lock_guard lock(mutex);\n  int local = counter;\n  ++local;\n  counter = local;\n} // unlock` : mode==="rmw"?`std::atomic<int> counter{0};\nint local = counter.fetch_add(1, std::memory_order_relaxed);\n// local receives the old value; counter is incremented.`:`std::atomic<int> counter{0};\nint local = counter.load(std::memory_order_relaxed);\n++local;\ncounter.store(local, std::memory_order_relaxed);\n// Separate local variable in each thread.`;
    const s=concurrencyInitial();s.mode=mode;
    const t=trace("concurrency",code,"C++20 · фрагмент операции каждого из двух потоков",s);
    t.scheduler=true;t.mode=mode;
    t.add(0,"Выбери порядок выполнения","Два потока увеличивают один общий счётчик. counter и, в варианте с замком, mutex созданы один раз до запуска потоков. Переменная local у каждого потока своя. Кнопками A и B можно построить собственное чередование с текущего шага; будущие шаги будут заменены.","Показан один допустимый порядок событий, а не модель физических кэшей. Оба потока затем нужно дождаться через join, прежде чем читать итог в основном потоке.",s);
    const schedule=mode==="mutex"?["A","B","A","A","A","A","B","B","B","B","B"]:mode==="rmw"?["A","B"]:["A","B","A","B","A","B"];
    let current=s;for(const who of schedule){const e=concurrencyStep(current,who,mode);if(e){t.steps.push(e);current=e.state;}}
    return t;
  }

  function network(mode,options={}) {
    if(["retry","dedup","version"].includes(mode))return api(mode);
    const wire=mode==="oversize"?[8,65,66,67]:[3,65,66,67,2,68,69];
    const chunks=options.chunks || (mode==="combined"?[wire.length]:mode==="oversize"?[1,3]:[1,2,1,3]);
    const code=`// Protocol: one length byte, then that many bytes.\n// Maximum body size: 5. A zero-length body is allowed.\nreceive_bytes(); // append, do not assume message boundary\nwhile (true) {\n  if (!expected && buffer.empty()) break;\n  if (!expected) { expected = take_length(); check_limit(); }\n  if (buffer.size() < *expected) break;\n  emit(take_body(*expected));\n  expected.reset();\n}`;
    const s={wire,received:0,buffer:[],expected:null,messages:[],rejected:false,chunks};
    const t=trace("network",code,"Псевдокод потокового парсера · не готовый Socket API",s);
    t.add(0,"Границы чтений не являются сообщениями","Первая запись содержит ABC, вторая — DE. Префиксы 03 и 02 — длины тел, не буквы. В варианте ошибки префикс 08 превышает допустимый предел.","Протокол здесь учебный. TCP переносит упорядоченный поток байтов.",s);
    let offset=0;
    for(const length of chunks){
      if(s.rejected)break;
      const data=wire.slice(offset,offset+length);offset+=data.length;s.received=offset;s.buffer.push(...data);
      t.add(2,"Получили ещё "+data.length+" байт","Новые байты добавлены к уже накопленным. Сам факт завершения чтения не означает готовности сообщения.","Один приём может дать часть записи или сразу несколько записей.",s,"Получено: "+data.map(n=>n.toString(16).padStart(2,"0")).join(" "));
      while(true){
        if(s.expected===null){if(!s.buffer.length)break;s.expected=s.buffer.shift();
          if(s.expected>5){s.rejected=true;t.add(5,"Длина превышает предел","Заявлено "+s.expected+" байт тела при максимуме 5. Парсер отвергает вход до ожидания такого тела.","Лимит проверяют после разбора длины и до выделения большого буфера.",s,"Протокольный отказ: oversized frame.");break;}
          t.add(5,"Прочитали длину "+s.expected,"Префикс снят с начала буфера. Теперь нужно ровно "+s.expected+" байт тела.","Состояние expected сохраняется между чтениями; префикс не читается повторно.",s);
        }
        if(s.buffer.length<s.expected){t.add(6,"Тело ещё не собрано","В буфере "+s.buffer.length+" байт, нужно "+s.expected+". Сохраняем их и ждём следующую порцию.","При окончательном EOF такое состояние означает оборванную запись, а не полное сообщение.",s);break;}
        const message=String.fromCharCode(...s.buffer.splice(0,s.expected));s.messages.push(message);s.expected=null;
        t.add(7,"Готово сообщение «"+message+"»","Из буфера извлечено ровно тело одной записи. Оставшиеся байты могут начать следующую запись, поэтому цикл продолжается.","Нельзя выбрасывать хвост буфера после первого сообщения.",s,"Доставлено приложению: "+message);
      }
    }
    if(!s.rejected)t.add(9,"Один поток — те же сообщения","Восстановлены ABC и DE. Сравни вариант, где все байты пришли одним чтением: содержание сообщений останется тем же.","Результат разбора должен зависеть от байтов протокола, а не от удачно выбранных границ receive.",s,"ABC, DE; буфер пуст.");
    return t;
  }
  function api(mode) {
    const version=mode==="version",dedup=mode==="dedup";
    const code=version?`GET /tasks/42 -> title=A, version=7\nX: PATCH title=B, If-Match: "v7"\n// compare version and write atomically\nY: PATCH title=C, If-Match: "v7"\n// stale precondition -> 412; no write`:`POST /tasks ${dedup?"Idempotency-Key: K":"(without operation key)"}\n// Server commits the creation.\n// The response is lost.\nPOST /tasks ${dedup?"Idempotency-Key: K":"(same command again)"}\n// ${dedup?"Same operation: return its recorded result.":"Independent command: may create another task."}`;
    const s={api:true,client:version?"X и Y сохранили A/v7":"Команда ещё не отправлена",server:version?"A / v7":"Нет новых задач",count:0,version:7,title:"A",left:"Клиент",right:"Сервис",message:"",direction:"right",lost:false,key:dedup?"K":null,record:false};
    const t=trace("network",code,"HTTP · договор и события, не исполняемый обработчик",s);
    t.add(0,version?"Два редактора прочитали v7":"Отделим факт от знания",version?"X и Y получили одно представление A/v7. Каждый намерен записать своё изменение.":"Состояние сервера и сведения клиента будут показаны отдельно. Тайм-аут меняет знания клиента, но сам по себе не отменяет запись.","Авторизация, валидация и проверка доступа считаются успешно пройденными.",s);
    if(version){
      Object.assign(s,{client:"X и Y прочитали A/v7",server:"A / v7",message:"PATCH X · expected v7"});t.add(1,"X отправляет своё изменение","Запрос X требует совпадения с текущим сильным тегом. Сравнение и запись — одна операция хранилища.","Отдельная проверка до безусловной записи оставила бы окно для гонки.",s);
      Object.assign(s,{version:8,title:"B",server:"B / v8",client:"X получил успех; у Y ещё v7",direction:"left",message:"200 · новое представление B/v8"});t.add(2,"Изменение X применено","Версия стала 8. Снимок Y не обновляется автоматически.","Mutex сам по себе не проверяет свежесть пользовательского решения.",s,"X: применено; текущее B/v8.");
      Object.assign(s,{direction:"right",message:"PATCH Y · expected v7"});t.add(3,"Y отправляет устаревшее условие","Версия v7 уже не подходит. По выбранному договору запрос отклоняется без изменения полей.","Нельзя молча подставить v8 и отправить старое полное состояние: это уберёт защиту от потери изменения.",s);
      Object.assign(s,{direction:"left",message:"412 Precondition Failed",client:"Y узнал о конфликте"});t.add(4,"Конфликт обнаружен","Текущее состояние всё ещё B/v8. Y нужно перечитать ресурс и согласовать новое намерение.","Отказ и чтение не увеличивают версию.",s,"Y: 412; состояние B/v8.");
    }else{
      s.message="POST создать задачу"+(dedup?" · K":"");s.client="Запрос отправлен; ждёт ответ";t.add(0,"Первая попытка дошла до сервера","Сервис принимает команду создания.",dedup?"Ключ относится к одной операции в области пользователя и endpoint.":"Одинаковый JSON сам по себе не связывает команды с одной операцией.",s);
      Object.assign(s,{count:1,server:"Задача 42 создана",record:dedup,direction:"left",message:"201 · /tasks/42",lost:true});t.add(1,"Запись есть, ответ потерялся","Сервис создал задачу, но ответ не дошёл. Клиент пока не знает, был ли эффект.",dedup?"В этом опыте эффект и результат ключа уже согласованно сохранены, сервер не перезапускался.":"Потеря ответа не является откатом.",s,"Сервер: одна задача. Клиент: результата нет.");
      s.client="Тайм-аут: исход неизвестен";s.message="Ответ не получен";t.add(2,"Клиент перестаёт ждать","Клиентский срок истёк. Это не команда базе отменить уже зафиксированные данные.","Нельзя по одному тайм-ауту заключить, что обработчик не запускался.",s);
      Object.assign(s,{direction:"right",lost:false,message:dedup?"Повтор POST · тот же K":"Повтор POST · без ключа"});t.add(3,"Повторяем попытку",dedup?"Та же операция K с тем же телом находит сохранённый результат.":"Новая HTTP-команда не имеет устойчивой связи с первой. Сервис может создать ещё одну задачу.","Задержка повтора и новое TCP-соединение не решают вопрос повторного эффекта.",s);
      Object.assign(s,{count:dedup?1:2,server:dedup?"Одна задача 42":"Созданы задачи 42 и 43",client:dedup?"Получил результат K: задача 42":"Получил успех второй команды: задача 43",direction:"left",message:dedup?"Сохранённый результат /tasks/42":"201 · /tasks/43"});t.add(4,dedup?"Результат повторён, эффект — нет":"Получился второй эффект",dedup?"Создания новой задачи не было. Устойчивость этого обещания при сбое процесса нужно обеспечивать отдельно: одна таблица ключей в RAM не решает все окна отказа.":"Оба запроса создали по задаче. Клиент мог хотеть только одну, но без договора сервис не распознал это намерение.","Сравни соседний вариант с другим правилом повторов.",s,dedup?"Задач: 1; повтор узнал сохранённый результат.":"Задач: 2; повтор продублировал создание.");
    }
    return t;
  }

  function sql(mode) {
    const countStar=mode==="count-star",where=mode==="where",inner=mode==="inner";
    const count=countStar?"COUNT(*)":"COUNT(t.id)";
    const lines=["SELECT u.id, u.name, "+count+" AS open_tasks","FROM users AS u",(inner?"JOIN":"LEFT JOIN")+" tasks AS t","  ON t.owner_id = u.id"+(where?"":" AND t.done = false")];
    if(where)lines.push("WHERE t.done = false");lines.push("GROUP BY u.id, u.name","ORDER BY u.id;");
    const s={mode,stage:"sources",users:[{id:1,name:"Анна"},{id:2,name:"Борис"},{id:3,name:"Вера"}],tasks:[{id:10,owner:1,done:false},{id:11,owner:1,done:true},{id:12,owner:2,done:false}],pairs:[],rows:[]};
    const t=trace("sql",lines.join("\n"),"SQL · PostgreSQL; логические этапы, не физический план",s);
    t.add(1,"Две исходные таблицы","У Анны две задачи, из которых одна завершена; у Бориса одна открытая; у Веры нет задач. Требуется показать всех пользователей и число открытых задач.","Одна строка tasks — одна задача. Пользователь и задача имеют разные идентификаторы.",s);
    for(const u of s.users){const matches=s.tasks.filter(task=>task.owner===u.id&&(where||!task.done));for(const task of matches)s.pairs.push({user:u.id,name:u.name,task:task.id,done:task.done});if(!matches.length&&!inner)s.pairs.push({user:u.id,name:u.name,task:null,done:null});}
    s.stage="join";t.add(3,"Строим пары по условию ON",where?"Условие ON пока проверяет только владельца, поэтому соединяет и завершённую задачу 11. LEFT JOIN добавляет строку Веры с NULL справа.":inner?"INNER JOIN оставляет только совпавшие открытые задачи. Для Веры пары нет, поэтому строка Веры уже потеряна.":"ON сопоставляет только открытые задачи. LEFT JOIN сохраняет Веру, дополняя правые столбцы NULL.","Картинки пересечения кругов не объясняют размножение пар: здесь показаны сами строки.",s,"После JOIN строк: "+s.pairs.length);
    if(where){s.pairs=s.pairs.filter(p=>p.done===false);s.stage="where";t.add(4,"WHERE отбрасывает и строку Веры","У Веры t.done равно NULL. Сравнение NULL = false не даёт true, а WHERE оставляет только true. Поэтому Вера исчезла вместе с завершённой задачей Анны.","Условие в ON определяет подходящие пары; WHERE фильтрует уже полученный результат соединения.",s,"Остались только пары Анна–10 и Борис–12.");}
    const grouped=new Map();for(const p of s.pairs){if(!grouped.has(p.user))grouped.set(p.user,{id:p.user,name:p.name,count:0,taskIds:[]});const g=grouped.get(p.user);if(countStar||p.task!==null)g.count++;g.taskIds.push(p.task);}
    s.rows=[...grouped.values()].sort((a,b)=>a.id-b.id);s.stage="groups";
    t.add(lines.length-2,"Собираем группы по пользователю",countStar?"COUNT(*) считает строки результата JOIN. Дополненная строка Веры тоже строка: её счётчик ошибочно стал 1.":where||inner?"После предыдущего этапа остались только пары Анна–10 и Борис–12. COUNT(t.id) даёт по 1 для их групп. Строки Веры уже нет: GROUP BY и COUNT не создадут для неё отсутствующую группу с нулём.":"COUNT(t.id) учитывает только значения, отличные от NULL. У сохранённой строки Веры нет настоящей задачи, поэтому получается 0.","Числовой ноль тоже учитывается COUNT(expr). Исключается именно NULL.",s,"Групп: "+s.rows.length);
    s.stage="result";t.add(lines.length-1,"Проверяем результат по требованию",where||inner?"Получились Анна: 1 и Борис: 1. Вера отсутствует — запрос не выполнил требование показать всех пользователей.":countStar?"Все пользователи сохранились, но у Веры ложная единица. В этом запросе для задач нужен COUNT(t.id).":"Результат: Анна: 1, Борис: 1, Вера: 0. Нужный состав пользователей и смысл счётчика сохранены.","Сравни соседние варианты, затем напиши собственный запрос в SQL-тренажёре.",s,s.rows.map(r=>r.name+": "+r.count).join("; "));
    return t;
  }

  function transactions(mode) {
    const snapshot=mode==="rc"||mode==="rr",rollback=mode==="rollback";
    if(snapshot){
      const rr=mode==="rr";
      const code=`-- Session A\nBEGIN ISOLATION LEVEL ${rr?"REPEATABLE READ":"READ COMMITTED"};\nSELECT value FROM counter WHERE id = 1;\n-- Session B, separate transaction\nBEGIN;\nUPDATE counter SET value = 110 WHERE id = 1;\nCOMMIT;\n-- Session A, same transaction as before\nSELECT value FROM counter WHERE id = 1;\nCOMMIT;`;
      const s={snapshot:true,mode,database:100,a:null,b:null,lock:null,aStatus:"Не начата",bStatus:"Не начата",waiting:false,winners:0};
      const t=trace("transactions",code,"SQL · две отдельные сессии PostgreSQL 18",s);
      t.add(1,"Одна строка со значением 100","Сессия A начнёт транзакцию уровня "+(rr?"Repeatable Read":"Read Committed")+". Сессия B изменит данные между двумя чтениями A.","Обычные SELECT без FOR UPDATE. Собственных записей в A нет.",s);
      s.a=100;s.aStatus="Первый SELECT: 100";t.add(2,"A читает первый снимок","Первое обычное чтение A возвращает 100.",rr?"В PostgreSQL RR снимок устанавливается первым содержательным оператором, не одним BEGIN.":"В RC обычный SELECT получает снимок на начало команды.",s,"A → 100");
      Object.assign(s,{database:110,b:110,bStatus:"Изменила и зафиксировала"});t.add(6,"B фиксирует значение 110","Зафиксированное состояние базы изменилось. Обычное чтение A не удерживало запрет на такую запись.","Не путаем снимок с блокировкой строки для изменения.",s,"База → 110; первое прочитанное A остаётся 100.");
      s.a=rr?100:110;s.aStatus="Второй SELECT: "+s.a;t.add(8,"A читает ещё раз",rr?"Повторный SELECT в той же RR-транзакции использует прежний снимок и снова возвращает 100.":"Новая команда RC видит фиксацию B и возвращает 110.",rr?"Стабильный снимок не равен полной сериализуемости межстрочных решений.":"Это неповторяемое чтение, а не чтение незафиксированной чужой записи.",s,"A → "+s.a+"; база → 110.");
      s.aStatus="Завершена";t.add(9,"Транзакция A завершена","Зафиксированных изменений A нет: она только читала. Значение базы остаётся 110.","Здесь сравниваем PostgreSQL, а не все СУБД под теми же именами уровней.",s);
      return t;
    }
    const code=`-- Two sessions; execute each command in its session.\n-- Session A\nBEGIN ISOLATION LEVEL READ COMMITTED;\nUPDATE parking SET available = available - 1\nWHERE id = 1 AND available > 0 RETURNING available;\n-- Session B\nBEGIN ISOLATION LEVEL READ COMMITTED;\nUPDATE parking SET available = available - 1\nWHERE id = 1 AND available > 0 RETURNING available;\n-- Session A\n${rollback?"ROLLBACK":"COMMIT"};\n-- Session B: its UPDATE can now finish\nCOMMIT;`;
    const s={snapshot:false,mode,database:1,a:null,b:null,lock:null,aStatus:"Не начата",bStatus:"Не начата",waiting:false,winners:0};
    const t=trace("transactions",code,"SQL · последнее место, PostgreSQL Read Committed",s);
    t.add(0,"Свободно одно место","Оба запроса хотят занять последнее место. Проверка available > 0 и уменьшение находятся в одном UPDATE.","Результат UPDATE ещё не означает подтверждённое бронирование: нужен COMMIT.",s);
    Object.assign(s,{a:0,lock:"A",aStatus:"UPDATE вернул 0; ещё не COMMIT"});t.add(3,"A изменила строку внутри транзакции","A получила одну изменённую строку со значением 0. Для обычного внешнего читателя по-прежнему видна зафиксированная 1; A удерживает блокировку строки.","Разделяй новое локальное состояние транзакции и зафиксированное состояние.",s,"A: одна строка; локально available=0.");
    Object.assign(s,{waiting:true,bStatus:"Ждёт завершения A"});t.add(7,"B ждёт ту же строку","Конкурирующий UPDATE B не может завершить изменение, пока A удерживает конфликтующую блокировку.","B пока не получила ни успех, ни результат «мест нет».",s,"B: ожидание row lock.");
    Object.assign(s,{database:rollback?1:0,a:null,aStatus:rollback?"Откатилась":"Зафиксировала",lock:null,winners:rollback?0:1});t.add(10,rollback?"A откатывается":"A фиксирует изменение",rollback?"Уменьшение A отменено. Зафиксированное available остаётся 1, блокировка освобождена.":"available=0 становится зафиксированным состоянием. A получила место; B может продолжить проверку.","После освобождения блокировки B действует по правилам Read Committed.",s,rollback?"A: ROLLBACK; available=1.":"A: COMMIT; available=0.");
    s.waiting=false;
    if(rollback){Object.assign(s,{b:0,lock:"B",bStatus:"UPDATE вернул 0; ещё не COMMIT"});t.add(7,"Теперь место получает B","Изменение A отменено. B может применить свой UPDATE: available уменьшается с 1 до 0 внутри B.","Это ещё не второй успех: попытка A была отменена.",s,"B: одна строка; локально available=0.");}
    else {s.bStatus="UPDATE вернул 0 строк";s.lock="B";t.add(7,"B повторно проверяет условие","B заблокировала обновлённую версию строки для повторной проверки. Теперь available=0: условие available>0 ложно, поэтому B не меняет ни одной строки. Полученную блокировку B удерживает до конца своей транзакции.","UPDATE с нулём строк — не SQL-ошибка и не доказательство отсутствия блокировок. Здесь блокировка появилась при перепроверке после ожидания A.",s,"B: 0 строк; available=0; блокировка B остаётся до COMMIT.");}
    Object.assign(s,{database:0,b:null,lock:null,bStatus:"Завершена",winners:1});t.add(12,"Итог — одно занятое место","Обе транзакции завершены. Зафиксированное available=0; ровно одна попытка получила место.","Потеря ответа после COMMIT требует отдельного договора повторов. Этот опыт не обещает идемпотентность бронирования.",s,"Зафиксированных бронирований: 1; свободных мест: 0.");
    return t;
  }

  function overload(mode,options={}) {
    const rate=Math.max(0,Math.min(12,Math.trunc(Number(options.rate ?? 8))||0));
    const workers=Math.max(1,Math.min(8,Math.trunc(Number(options.workers ?? 4))||1));
    const queue=Math.max(0,Math.min(20,Math.trunc(Number(options.queue ?? 8))||0));
    const code=`// A discrete model, each task takes exactly one tick.\ncapacity = workers + queue_limit;\naccepted = draining ? 0 : min(arrivals, capacity - pending);\nrejected = arrivals - accepted;\npending += accepted;\ncompleted = min(workers, pending);\npending -= completed;\n// Next tick: pending is the waiting queue.`;
    const s={mode,rate,workers,queue,pending:0,arrived:0,accepted:0,rejected:0,completed:0,lastAccepted:0,lastRejected:0,lastCompleted:0,time:0,phase:"Serving",history:[]};
    const t=trace("overload",code,"Псевдокод дискретной модели, не нагрузочный замер",s);t.parameters={rate,workers,queue};
    t.add(0,"Зададим правила эксперимента","За секунду приходит "+rate+" задач, каждый из "+workers+" исполнителей завершает одну задачу за такт. Кроме работающих задач можно удерживать ещё "+queue+" ожидающих.","В начале такта поступает пакет задач; в конце завершается работа исполнителей. Длительности здесь фиксированы.",s);
    for(let time=1;time<=10;time++){
      const draining=mode==="drain"&&time>=7;
      const accepted=draining?0:Math.min(rate,workers+queue-s.pending);
      const rejected=rate-accepted,completed=Math.min(workers,s.pending+accepted);
      s.pending+=accepted-completed;s.arrived+=rate;s.accepted+=accepted;s.rejected+=rejected;s.completed+=completed;s.time=time;s.lastAccepted=accepted;s.lastRejected=rejected;s.lastCompleted=completed;
      s.phase=draining?(s.pending?"Draining":"Stopped"):"Serving";s.history.push({time,pending:s.pending,rejected,completed});
      t.add(draining?2:rejected?3:5,"Секунда "+time+" · "+s.phase,draining?"Приём новой работы закрыт. Входящие запросы отклоняются, а уже принятые задачи продолжают завершаться.":rejected?"Все свободные места исчерпаны. Часть входящего пакета отклонена, поэтому очередь не растёт сверх предела.":"Новые задачи приняты в доступные места. Работа выполняется с заданной скоростью, остаток ждёт следующего такта.","Проверяй баланс: принято = завершено + осталось; поступило = принято + отклонено.",s,"За такт: принято "+accepted+", выполнено "+completed+", отклонено "+rejected+"; в очереди "+s.pending);
    }
    t.add(7,"Что изменил размер очереди",mode==="drain"?"После закрытия приёма новые запросы не продлевают очередь. Если исполнители продолжают работать, конечная очередь будет разобрана; показанных десяти тактов может не хватить при большой очереди.":"Буфер позволяет принять короткий всплеск, но не повышает скорость исполнителей. При постоянном превышении входного потока он заполняется и начинаются отказы.","Это не распределение реальной задержки. Закон Литтла применяют к средним в согласованных границах устойчивого режима.",s);
    return t;
  }

  global.CourseLabModels={ownership,vector,build,concurrency,concurrencyInitial,concurrencyStep,network,sql,transactions,overload,copy};
})(globalThis);
