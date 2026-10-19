/* Original course exercises. Engine: SQLite via vendored sql.js, not PostgreSQL. */
(function (root) {
  "use strict";
  const schema = `PRAGMA foreign_keys=ON;
CREATE TABLE users(id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE tasks(id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id),
 title TEXT NOT NULL CHECK(length(title)>0), done INTEGER NOT NULL DEFAULT 0 CHECK(done IN (0,1)),
 priority INTEGER CHECK(priority BETWEEN 1 AND 5));
INSERT INTO users VALUES(1,'Анна'),(2,'Борис'),(3,'Вера');
INSERT INTO tasks VALUES(10,1,'Написать тест',0,3),(11,1,'Обновить README',1,NULL),(12,2,'Проверить API',0,1);`;
  const variant = `INSERT INTO users VALUES(4,'Глеб');
INSERT INTO tasks VALUES(13,1,'Разобрать логи',0,5),(14,4,'Проверить лимит',1,NULL),(15,4,'Добавить метрику',0,2);`;
  const exercises = [
    ['expression','Первый SELECT','Верни одну строку с числом 5 в столбце result. Вычисли его как 2 + 3.',
      'SELECT 2 + 3 AS result;', 'После SELECT можно написать выражение; AS задаёт имя столбца.', 'sql-first-query'],
    ['columns','Столбцы и строки','Выведи id и title всех задач по возрастанию id. Исходную таблицу не меняй.',
      'SELECT id, title FROM tasks ORDER BY id;', 'SELECT выбирает столбцы, FROM — таблицу, ORDER BY — порядок строк.', 'sql-select-basics'],
    ['filter','Один фильтр','Выведи id и title задач владельца 1 по возрастанию id.',
      'SELECT id, title FROM tasks WHERE owner_id = 1 ORDER BY id;', 'WHERE проверяется для каждой строки. Здесь сравниваем owner_id, а не id задачи.', 'sql-filter-basics'],
    ['and','Два условия','Выведи id незавершённых задач владельца 1 по возрастанию id.',
      'SELECT id FROM tasks WHERE owner_id = 1 AND done = false ORDER BY id;', 'Оба условия должны быть истинны: используй AND.', 'sql-filter-basics'],
    ['null','Неизвестный приоритет','Выведи id задач без заданного priority по возрастанию id.',
      'SELECT id FROM tasks WHERE priority IS NULL ORDER BY id;', 'Отсутствие значения проверяется IS NULL, а не = NULL.', 'sql-null-basics'],
    ['sort','Первые две задачи','Выведи id и priority двух задач с самым большим известным приоритетом. Сначала больший priority; при равенстве — меньший id.',
      'SELECT id, priority FROM tasks WHERE priority IS NOT NULL ORDER BY priority DESC, id ASC LIMIT 2;', 'Сначала исключи NULL, затем задай два ключа сортировки и LIMIT.', 'sql-order-basics'],
    ['distinct','Владельцы без повторов','Выведи разные owner_id из tasks по возрастанию. Нужны владельцы задач, а не все users.',
      'SELECT DISTINCT owner_id FROM tasks ORDER BY owner_id;', 'DISTINCT убирает одинаковые строки результата.', 'sql-order-basics'],
    ['insert','Создать задачу','Добавь задачу (id=20, owner_id=1, title=Новая задача, done=false, priority=2). Все прежние строки должны сохраниться.',
      "INSERT INTO tasks(id,owner_id,title,done,priority) VALUES(20,1,'Новая задача',false,2);", 'Перечисли столбцы и значения в одинаковом порядке.', 'sql-write-basics','state'],
    ['update','Изменить одну строку','У задачи id=10 установи done=true. Не меняй другие поля и задачи.',
      'UPDATE tasks SET done = true WHERE id = 10;', 'SET задаёт новое значение. WHERE ограничивает изменение одной строкой.', 'sql-write-basics','state'],
    ['delete','Удалить завершённые','Удали только завершённые задачи владельца 1. Остальные задачи и пользователи должны сохраниться.',
      'DELETE FROM tasks WHERE owner_id = 1 AND done = true;', 'Без WHERE команда удалит все строки. Нужны оба условия.', 'sql-write-basics','state'],
    ['join','Задачи и имена','Выведи id задачи и имя её владельца в столбце owner_name для незавершённых задач. Порядок — id задачи.',
      'SELECT t.id, u.name AS owner_name FROM tasks AS t JOIN users AS u ON u.id=t.owner_id WHERE t.done=false ORDER BY t.id;', 'Соединяем owner_id задачи с id пользователя; t и u — псевдонимы.', 'worked-example'],
    ['group','Считаем задачи','Для каждого owner_id, присутствующего в tasks, выведи owner_id и число задач AS task_count. Порядок — owner_id.',
      'SELECT owner_id, COUNT(*) AS task_count FROM tasks GROUP BY owner_id ORDER BY owner_id;', 'GROUP BY объединяет строки в группы, COUNT(*) считает строки внутри каждой.', 'sql-aggregate-basics'],
    ['left','Не потерять Веру','Выведи id каждого пользователя и число его незавершённых задач AS open_count. Пользователь без таких задач получает 0. Порядок — id пользователя.',
      'SELECT u.id, COUNT(t.id) AS open_count FROM users AS u LEFT JOIN tasks AS t ON t.owner_id=u.id AND t.done=false GROUP BY u.id ORDER BY u.id;', 'Условие done помести в ON, а считай t.id, не COUNT(*).', 'aggregation'],
    ['having','Фильтруем группы','Выведи owner_id и COUNT(*) AS task_count только для владельцев с двумя и более задачами. Порядок — owner_id.',
      'SELECT owner_id, COUNT(*) AS task_count FROM tasks GROUP BY owner_id HAVING COUNT(*) >= 2 ORDER BY owner_id;', 'WHERE фильтрует строки до группировки, HAVING — полученные группы.', 'sql-aggregate-basics'],
    ['exists','Без открытых задач','Выведи id и name пользователей, у которых нет незавершённых задач. Включи пользователей вообще без задач. Порядок — id.',
      'SELECT u.id, u.name FROM users u WHERE NOT EXISTS (SELECT 1 FROM tasks t WHERE t.owner_id=u.id AND t.done=false) ORDER BY u.id;', 'NOT EXISTS проверяет отсутствие подходящей строки, не размножая пользователей.', 'sql-exists'],
    ['cte','Имена активных владельцев','Выведи имя пользователя и общее число его задач для владельцев с двумя и более задачами. Порядок — id пользователя. Попробуй выделить подсчёт в CTE.',
      'WITH counts AS (SELECT owner_id, COUNT(*) AS task_count FROM tasks GROUP BY owner_id) SELECT u.name, c.task_count FROM counts c JOIN users u ON u.id=c.owner_id WHERE c.task_count>=2 ORDER BY u.id;', 'Сначала одна строка на owner_id, затем JOIN с именами. Проверяется результат: эквивалентное решение без CTE тоже допустимо.', 'sql-cte-union'],
    ['window','По одной задаче владельца','Выведи id и owner_id задачи с наибольшим id для каждого владельца, имеющего задачи. Порядок — owner_id. Попробуй ROW_NUMBER.',
      'WITH ranked AS (SELECT id, owner_id, ROW_NUMBER() OVER (PARTITION BY owner_id ORDER BY id DESC) AS rn FROM tasks) SELECT id, owner_id FROM ranked WHERE rn=1 ORDER BY owner_id;', 'Оконную нумерацию вычисли внутри CTE, а фильтр rn=1 — снаружи. Максимальный id не обязательно означает последнее время создания.', 'sql-window-rank'],
    ['frame','Владелец и накопительный счётчик','Для каждой задачи выведи id, owner_id, общее число задач владельца и число его задач с id не больше текущего. Порядок — owner_id, id.',
      'SELECT id, owner_id, COUNT(*) OVER (PARTITION BY owner_id), COUNT(*) OVER (PARTITION BY owner_id ORDER BY id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) FROM tasks ORDER BY owner_id, id;', 'Первое окно видит всю группу, второе — строки от начала до текущей включительно.', 'sql-window-frame'],
    ['upsert','Вставить или обновить','Одним INSERT с ON CONFLICT создай пользователя id=1 с именем Анна Петрова или обнови его имя, если он существует. Другие данные не меняй.',
      "INSERT INTO users(id,name) VALUES(1,'Анна Петрова') ON CONFLICT(id) DO UPDATE SET name=excluded.name;", 'Конфликт проверяется по первичному ключу id. Проверка оценивает состояние данных, а не наличие конкретных ключевых слов.', 'sql-backend-boundaries','state'],
    ['report','Отчёт для API','Для каждого пользователя выведи id, name, число незавершённых задач и максимальный id среди них. При отсутствии открытых задач нужны 0 и NULL. Порядок — id пользователя.',
      'WITH o AS (SELECT owner_id, COUNT(*) AS n, MAX(id) AS last_id FROM tasks WHERE done=false GROUP BY owner_id) SELECT u.id,u.name,COALESCE(o.n,0),o.last_id FROM users u LEFT JOIN o ON o.owner_id=u.id ORDER BY u.id;', 'Агрегируй открытые задачи до LEFT JOIN. COALESCE нужен для счётчика, не для отсутствующего id.', 'sql-report-final-workbook']
  ].map(row => ({id:row[0],title:row[1],prompt:row[2],solution:row[3],hint:row[4],section:row[5],kind:row[6] || 'query'}));
  function seed(SQL, alternate) {
    const db = new SQL.Database();
    db.run(schema);
    if (alternate) db.run(variant);
    return db;
  }
  function snapshot(db) {
    return ['users','tasks'].map(name => {
      try { return {name, ...db.exec('SELECT * FROM '+name+' ORDER BY id')[0]}; }
      catch (_) { return {name,columns:[],values:[],missing:true}; }
    });
  }
  function execute(db, query) {
    const results=[];
    // Iterate instead of materialising arbitrarily many rows with db.exec().
    for (const statement of db.iterateStatements(query)) {
      try {
        const columns=statement.getColumnNames(), values=[];
        let truncated=false;
        while(statement.step()) {
          if(values.length >= 200) { truncated=true; break; }
          values.push(statement.get().map(x => typeof x==='string' && x.length>1000 ? x.slice(0,1000)+'…' : x));
        }
        if(columns.length) results.push({columns,values,truncated});
        if(truncated) break;
      } finally { statement.free(); }
    }
    return results;
  }
  function equalResult(actual, expected) {
    if(actual.length!==expected.length) return false;
    return actual.every((r,i) => !r.truncated && r.columns.length===expected[i].columns.length &&
      JSON.stringify(r.values)===JSON.stringify(expected[i].values));
  }
  function check(SQL, exercise, query) {
    // A second dataset catches answers hard-coded to the three visible rows.
    for (const alternate of [false,true]) {
      const db=seed(SQL,alternate), expectedDb=seed(SQL,alternate);
      try {
        const actual=execute(db,query), expected=execute(expectedDb,exercise.solution);
        if(JSON.stringify(snapshot(db))!==JSON.stringify(snapshot(expectedDb)))
          return {ok:false,reason:alternate ? 'На дополнительном наборе данных изменились не те строки.' : 'Состояние таблиц не совпало с условием. Проверь WHERE и сохранность других строк.'};
        if(exercise.kind==='query' && !equalResult(actual,expected))
          return {ok:false,reason:alternate ? 'На другом наборе строк ответ отличается. Не подставляй ID и имена вместо общего запроса.' : 'Проверь состав столбцов, значения, количество строк и заданный порядок.'};
      } finally {db.close();expectedDb.close();}
    }
    return {ok:true,reason:'Результат верен на двух наборах данных. Это проверка поведения, а не сравнение текста SQL.'};
  }
  function explainError(message) {
    if(/no such column/i.test(message)) return 'Не найден столбец. Проверь его имя и таблицу; текстовые значения пиши в одинарных кавычках.';
    if(/no such table/i.test(message)) return 'Не найдена таблица. Посмотри схему: users и tasks. Каждый запуск начинается с исходных данных.';
    if(/syntax error|incomplete input/i.test(message)) return 'Ошибка синтаксиса. Проверь запятые, кавычки, скобки и порядок частей запроса.';
    if(/UNIQUE constraint/i.test(message)) return 'Такой первичный ключ уже существует. Для новой строки нужен свободный id.';
    if(/FOREIGN KEY/i.test(message)) return 'Такого владельца нет в users. Внешний ключ не позволяет создать неверную ссылку.';
    if(/NOT NULL|CHECK constraint/i.test(message)) return 'Значение нарушает ограничение таблицы. Сверься со схемой.';
    return 'Проверь запрос. Это SQLite: специфические команды PostgreSQL (например FOR UPDATE) здесь не поддерживаются.';
  }
  root.SqlLab={schema,variant,exercises,seed,snapshot,execute,check,equalResult,explainError};
})(globalThis);
