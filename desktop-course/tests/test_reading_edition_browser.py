#!/usr/bin/env python3
"""Exercise the shared reading edition in offline Chrome. No user profile.

  /usr/bin/python3 desktop-course/tests/test_reading_edition_browser.py --roadmap build/local/roadmap
"""
import json
import os

from cdp import ROOT
from test_lab_interactions_browser import main as chrome, enter, capture


def stations():
    for source in sorted((ROOT.parent / 'roadmap/content').glob('station*.json')):
        data = json.loads(source.read_text())
        yield data['meta']['sourceFile'], data


def fit(page, name):
    widths = page.js('[document.documentElement.scrollWidth,document.documentElement.clientWidth]')
    assert widths[0] <= widths[1] + 1, (name, widths)


def lessons(page, prefix, width, out):
    page.viewport(width, 860)
    page.call('Log.enable')
    page.call('Network.emulateNetworkConditions', {'offline': True, 'latency': 0,
              'downloadThroughput': 0, 'uploadThroughput': 0})
    page.goto(prefix + 'cpp_backend_roadmap.html', "!!document.querySelector('.edition-cover h1')")
    assert page.js("document.querySelectorAll('.edition-index a').length===6")
    fit(page, 'cover')
    samples = figures = all_sections = all_panels = 0
    for filename, data in stations():
        sections = data['theory']
        page.goto(prefix + filename + '#section=' + sections[0]['id'],
                  "!!document.querySelector('body.edition-reader article .edition-opening')")
        assert page.js("document.querySelector('article .section-title').textContent") == sections[0]['title']
        fit(page, filename)
        if width == 375 and os.environ.get('COURSE_ALL_LESSONS') == '1':
            # Follow real fragment navigation and allow React and layout to settle.
            # Batch within one station; short CDP calls also identify the station on failure.
            for start in range(0, len(sections), 12):
                ids = [s['id'] for s in sections[start:start+12]]
                result = page.js("""(async ids => {
                  const frame=()=>new Promise(r=>requestAnimationFrame(r)), problems=[];
                  let checked=0;
                  for (const id of ids) {
                    location.hash='section='+id;
                    let found=false;
                    for(let i=0;i<40;i++){
                      await frame();
                      if(document.querySelector('article')?.dataset.termsScope===id){found=true;break;}
                    }
                    if(!found){problems.push([id,'route']);continue;}
                    const doc=document.documentElement;
                    if(doc.scrollWidth>doc.clientWidth+1) problems.push([id,doc.scrollWidth,doc.clientWidth]);
                    const wanted=window.STATION_DATA.theory.find(x=>x.id===id).blocks.filter(b=>typeof b.verifiedOutput==='string');
                    const panels=[...document.querySelectorAll('article .example-result')];
                    if(wanted.length!==panels.length){problems.push([id,'missing or duplicate output']);continue;}
                    panels.forEach((p,i)=>{
                      const b=wanted[i], code=p.closest('figure')?.querySelector('.code-block code');
                      if(code?.textContent!==b.code || (p.querySelector('.example-stdout samp')?.textContent??'')!==b.verifiedOutput ||
                         (!b.verifiedOutput && !p.querySelector('.example-silent')) ||
                         (p.querySelector('.example-testcase samp')?.textContent??'')!==(b.verifiedInput??'')) problems.push([id,'result not paired to source or input']);
                    });
                    checked+=panels.length;
                  }
                  return {problems,checked};
                })(""" + json.dumps(ids) + ")")
                assert not result['problems'], (filename, result['problems'])
                all_sections += len(ids)
                all_panels += result['checked']
        # Exercise a real, versioned result in each station that has one, plus
        # every new boundary drawing. No C++ or shell code is executed here.
        targets = page.js("""(() => {
          const xs = window.STATION_DATA.theory;
          const first = xs.find(x => x.blocks.some(b => typeof b.verifiedOutput === 'string'));
          const figs = xs.filter(x => x.blocks.some(b => ['reading-figure','time-chart'].includes(b.type)));
          return [...new Set([first,...figs].filter(Boolean).map(x=>x.id))];
        })()""")
        for section_id in targets:
            page.goto(prefix + filename + '#section=' + section_id,
                      "document.querySelector('article')?.dataset.termsScope===" + json.dumps(section_id))
            fit(page, filename + '#' + section_id)
            expected = page.js("window.STATION_DATA.theory.find(x=>x.id===" + json.dumps(section_id) +
                               ").blocks.filter(b=>typeof b.verifiedOutput==='string').map(b=>[b.code,b.verifiedOutput])")
            sels = page.js("[...document.querySelectorAll('article figure.code-wrap')].map((f,i)=>f.querySelector('.example-result')?i+1:0).filter(Boolean)")
            assert len(expected) == len(sels), (filename, section_id)
            for ix, (source, output) in zip(sels, expected):
                box = "article figure.code-wrap"  # Use the data order, not CSS sibling order.
                page.js("document.querySelectorAll(" + json.dumps(box) + ")[" + str(ix-1) + "].dataset.readingTest='output'")
                target = 'article figure[data-reading-test=output]'
                panel = target + ' .example-result'
                assert page.js('document.querySelector('+json.dumps(target+' pre code')+').textContent') == source
                if not page.js('document.querySelector('+json.dumps(panel)+').open'):
                    enter(page, panel + ' summary')
                page.wait('document.querySelector('+json.dumps(panel)+').open')
                if output:
                    assert page.js('document.querySelector('+json.dumps(panel+' .example-stdout samp')+').textContent') == output
                else:
                    assert page.js('!!document.querySelector('+json.dumps(panel+' .example-silent')+')')
                if samples == 0:
                    capture(page, panel, 'reading-output-' + str(width), out)
                enter(page, panel + ' summary')
                page.js('delete document.querySelector('+json.dumps(target)+').dataset.readingTest')
                samples += 1
            expected_figures = next(s for s in sections if s['id'] == section_id)['blocks']
            expected_figures = [b for b in expected_figures if b['type'] in ('reading-figure', 'time-chart')]
            assert page.js("document.querySelectorAll('article .reading-figure').length") == len(expected_figures)
            for figure_no, block in enumerate(expected_figures):
                ctx = (filename, section_id, width)
                if block['type'] == 'time-chart':
                    spans = page.js("""(i=>[...document.querySelectorAll('article .reading-figure')[i]
                      .querySelectorAll('.rf-interval')].map(l=>{
                        const svg=l.querySelector('svg'), bar=svg.querySelector('rect');
                        const s=svg.getBoundingClientRect(), r=bar.getBoundingClientRect();
                        return [l.querySelector('dt').textContent,l.querySelector('.rf-time-range').textContent,
                                (r.x-s.x)/s.width,r.width/s.width];
                      }))(""" + str(figure_no) + ")")
                    assert len(spans) == len(block['intervals']), ctx
                    for (label, note, left, length), item in zip(spans, block['intervals']):
                        a, b, unit = item['start'], item['end'], block['unit']
                        assert (label, note) == (item['label'], f'{a}–{b} {unit} · {b-a} {unit}'), ctx
                        assert abs(left - a/block['duration']) < .002 and abs(length - (b-a)/block['duration']) < .002, ctx
                    capture(page, 'article .rf-time', section_id + '-' + str(width), out)
                    figures += 1
                    continue
                actual = page.js(r"""(i => {
                  const f=document.querySelectorAll('article .reading-figure')[i];
                  const texts=els=>Array.from(els,x=>x.textContent);
                  const cells=Array.from(f.querySelectorAll('.rf-cell'));
                  const head=f.querySelector('.rf-mobile-key'), rect=f.getBoundingClientRect();
                  // Compare real opaque CSS surfaces, including inherited SQL table defaults.
                  const rgb=value=>value.match(/\d+(?:\.\d+)?/g).map(Number);
                  const luminance=v=>v.slice(0,3).reduce((sum,n,i)=>{
                    const s=n/255; return sum+[.2126,.7152,.0722][i]*(s<=.04045?s/12.92:((s+.055)/1.055)**2.4);
                  },0);
                  const contrast=el=>{
                    let bg=el;
                    while(bg && (rgb(getComputedStyle(bg).backgroundColor)[3]??1)===0) bg=bg.parentElement;
                    if(!bg)return 0;
                    const a=luminance(rgb(getComputedStyle(el).color)),b=luminance(rgb(getComputedStyle(bg).backgroundColor));
                    return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);
                  };
                  return {
                    title:f.querySelector('figcaption').textContent, caption:f.lastElementChild.textContent,
                    values:texts(f.querySelectorAll('.rf-cell strong')), notes:texts(f.querySelectorAll('.rf-cell span')),
                    cols:texts(f.querySelectorAll('th[scope=col]')), rows:texts(f.querySelectorAll('th[scope=row], dt')),
                    steps:texts(f.querySelectorAll('.rf-step')), lists:f.querySelectorAll('ul[role=list]').length,
                    localLabels:head&&getComputedStyle(head).display!=='none',
                    faint:[...f.querySelectorAll('th,dt,strong,span,small')].filter(el=>
                      el.getClientRects().length && contrast(el)<4.5).map(el=>el.textContent),
                    fits:cells.every(c=>{
                      const b=c.getBoundingClientRect(); return b.width>0 && b.height>0 &&
                        c.scrollWidth<=c.clientWidth+1 && b.left>=rect.left-1 && b.right<=rect.right+1;
                    })
                  };
                })(""" + str(figure_no) + ")")
                assert actual['fits'], ctx
                assert not actual['faint'], (ctx, actual['faint'])
                assert (actual['title'], actual['caption']) == (block['title'], block['caption']), ctx
                cells = [c for row in block['rows'] for c in row['cells']]
                assert actual['values'] == [c['value'] for c in cells], ctx
                assert actual['notes'] == [c['note'] for c in cells], ctx
                assert actual['rows'] == [row['label'] for row in block['rows']], ctx
                assert actual['cols'] == block.get('columns', []), ctx
                if block.get('layout') == 'matrix' and width <= 375:
                    assert actual['localLabels'] == (not block.get('compact', False)), ctx
                if block.get('layout') == 'flow':
                    assert actual['steps'] == [str(j+1) for row in block['rows'] for j in range(len(row['cells']))], ctx
                if block.get('layout') == 'compare':
                    assert actual['lists'] == len(block['rows']), ctx
                selector = 'article .reading-figure[data-qa-figure]'
                page.js("document.querySelectorAll('article .reading-figure')[" + str(figure_no) + "].dataset.qaFigure=''")
                capture(page, selector, section_id + '-' + str(figure_no+1) + '-' + str(width), out)
                page.js("delete document.querySelector(" + json.dumps(selector) + ").dataset.qaFigure")
                figures += 1
    assert samples > 0 and figures >= 4, (samples, figures)
    errors = [e['params']['entry']['text'] for e in page.events if
              e['method'] == 'Log.entryAdded' and e['params']['entry'].get('level') == 'error']
    assert not errors, errors
    print(f'{width}px: all station entrances; {samples} output panels, {figures} illustrations', flush=True)
    if all_sections:
        print(f'{all_sections} lessons rendered; all {all_panels} results paired to their sources and inputs', flush=True)


if __name__ == '__main__':
    chrome(lambda page, root, width, out: lessons(page, root.as_uri() + '/', width, out),
           'PASS: offline shared reading edition at desktop and mobile sizes', widths=(1280, 375, 320))
