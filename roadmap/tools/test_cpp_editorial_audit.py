"""Guard template spellings in rendered prose and targeted assessment gaps."""
import json
import unittest
import test_expanded_examples
from html.parser import HTMLParser
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ALLOWED=set('p b strong em i code pre a ul li ol div span table thead tbody tr th td figure figcaption h2 h3 h4 br details summary small sup sub'.split())

class ProseParser(HTMLParser):
    def __init__(self, point_lesson=False):
        super().__init__();self.unknown=[];self.text=[]
        self.point_lesson=point_lesson
        self.in_point_story=False
    def handle_starttag(self,tag,attrs):
        if self.point_lesson and tag == 'point-call-story' and not self.in_point_story:
            self.in_point_story=True
            return
        if self.in_point_story and tag in {'button', 'samp'}: return
        if tag not in ALLOWED:self.unknown.append(tag)
    def handle_endtag(self,tag):
        if self.in_point_story and tag == 'point-call-story':
            self.in_point_story=False
            return
        if self.in_point_story and tag in {'button', 'samp'}: return
        if tag not in ALLOWED:self.unknown.append(tag)
    def handle_data(self,data):self.text.append(data)

def prose(value):
    if isinstance(value,dict):
        for key,item in value.items():
            if key=='html':yield item
            else:yield from prose(item)
    elif isinstance(value,list):
        for item in value:yield from prose(item)

class CppEditorialAudit(unittest.TestCase):
    check_cpp = test_expanded_examples.ExpandedExamples.check_cpp

    def test_constexpr_reference_does_not_freeze_referent(self):
        self.check_cpp('''#include <iostream>
int counter = 0;
constexpr int& ref = counter;
int main() { ref = 7; std::cout << counter; }
''', '7')

    def test_unused_copy_member_is_not_instantiated(self):
        source = '''#include <memory>
template<class T> struct Box {
    T value;
    T copy() const { return value; }
};
int main() { Box<std::unique_ptr<int>> box{std::make_unique<int>(7)};
    return *box.value != 7;
}
'''
        self.check_cpp(source, '')
        self.check_cpp(source.replace('return *box.value != 7;', 'auto other = box.copy();'), valid=False)

    def test_sfinae_question_contains_its_own_context(self):
        data=json.loads((ROOT/'content/station3.json').read_text())
        question=next(q for q in data['quizzes']['advanced'] if q['q'].startswith('Что произойдёт при вызове length(5)'))
        source=question['q'].split('\n\n',1)[1]
        self.check_cpp(source+'\nint main() { return length(5); }', valid=False)
        self.check_cpp(source.replace('return x.size();','return 1;')+'\nint main() { return length(5) != 1; }', '')

    def test_no_cpp_templates_interpreted_as_html(self):
        for n in range(5):
            data=json.loads((ROOT/f'content/station{n}.json').read_text())
            for section in data['theory']:
                with self.subTest(station=n,section=section['id']):
                    for fragment in prose(section):
                        parser=ProseParser(point_lesson=(n == 0 and section['id'] == 'this'));parser.feed(fragment)
                        self.assertEqual(parser.unknown,[])
                        self.assertFalse(parser.in_point_story)

    def test_only_the_named_pilot_can_host_interactive_tags(self):
        component='<point-call-story><button></button><samp></samp></point-call-story>'
        approved=ProseParser(point_lesson=True)
        approved.feed(component+'<samp></samp><T>')
        self.assertEqual(approved.unknown,['samp','samp','t'])
        elsewhere=ProseParser();elsewhere.feed(component)
        self.assertEqual(elsewhere.unknown,['point-call-story','button','button','samp','samp','point-call-story'])

    def test_important_template_spellings_survive_rendering(self):
        for n,sid,spellings in [
            (1,'const-and-aliases',['unique_ptr<int>','unique_ptr<const int>']),
            (2,'nvi-interface-evolution',['unique_ptr<Base>','unique_ptr<Derived>']),
            (4,'expected-composition',['optional<int>','expected<int, ParseError>'])]:
            data=json.loads((ROOT/f'content/station{n}.json').read_text())
            section=next(s for s in data['theory'] if s['id']==sid)
            parser=ProseParser();parser.feed(' '.join(prose(section)))
            for spelling in spellings:self.assertIn(spelling,''.join(parser.text))

    def test_targeted_topics_have_assessment(self):
        sections=['valid-states-factories','smart-ptr-deep','nvi-interface-evolution','templates-class','external-effects-guarantees']
        for n,sid in enumerate(sections):
            data=json.loads((ROOT/f'content/station{n}.json').read_text())
            self.assertTrue(any(sid in q['theoryRefs'] for q in data['quizzes']['basic']),sid)

if __name__=='__main__':unittest.main()
