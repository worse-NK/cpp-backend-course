// Run: gjs roadmap/tools/test_quiz_shuffle.js
// Test the production helper without exporting UI internals.
const GLib = imports.gi.GLib;
const ByteArray = imports.byteArray;
function read(path) {
    const [ok, bytes] = GLib.file_get_contents(path);
    if (!ok) throw new Error("Cannot read " + path);
    return ByteArray.toString(bytes);
}
function assert(condition, message) {
    if (!condition) throw new Error(message);
}
const app = read("roadmap/assets/station-app.js");
new Function(app); // Syntax-check the complete renderer as well as the helper.
const helper = app.slice(app.indexOf("  function prepareQuestions("),
                         app.indexOf("  function Quiz(props)"));
const prepare = new Function(helper + "\nreturn prepareQuestions;")();
let checked = 0;
const contentDir = GLib.Dir.open("roadmap/content", 0);
const stationNumbers = [];
for (let name; (name = contentDir.read_name()) !== null;) {
    const match = /^station(\d+(?:-[a-z]+)?)\.json$/.exec(name);
    if (match) stationNumbers.push(match[1]);
}
stationNumbers.sort((a, b) => a.localeCompare(b));
assert(stationNumbers.length > 0, "No stations found");
for (const station of stationNumbers) {
    const data = JSON.parse(read("roadmap/content/station" + station + ".json"));
    Object.values(data.quizzes).forEach(questions => {
        const original = JSON.stringify(questions);
        questions.forEach(q => { Object.freeze(q.options); Object.freeze(q); });
        Object.freeze(questions);
        for (let attempt = 0; attempt < 20; attempt++) {
            const shuffled = prepare(questions);
            shuffled.forEach((q, i) => {
                assert(q.q === questions[i].q, "Question order changed");
                assert(JSON.stringify(q.theoryRefs) === JSON.stringify(questions[i].theoryRefs),
                       "Theory references lost");
                assert(q.substation === questions[i].substation, "Substation changed");
                assert(q.options[q.answer] === questions[i].options[questions[i].answer],
                       "Correct answer lost");
                assert(JSON.stringify(q.options.slice().sort()) ===
                       JSON.stringify(questions[i].options.slice().sort()), "Options lost");
                assert(q !== questions[i] && q.options !== questions[i].options,
                       "Shared mutable question");
                checked++;
            });
        }
        assert(JSON.stringify(questions) === original, "Source mutated");
    });
}
const originalRandom = Math.random;
const positions = new Set();
try {
    for (const value of [0, 0.25, 0.34, 0.999]) {
        Math.random = () => value;
        positions.add(prepare([{options: ["right", "b", "c", "d"], answer: 0}])[0].answer);
    }
} finally {
    Math.random = originalRandom;
}
assert(positions.size === 4, "Not all answer positions reachable");
print("PASS: " + checked + " shuffled questions; answer mapping and immutability.");
