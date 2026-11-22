#!/usr/bin/env python3
"""Exercise the station 0 scroll story in a clean, offline Chrome profile.

  /usr/bin/python3 desktop-course/tests/test_point_call_story_browser.py \
      --roadmap build/local/roadmap --screenshots build/this-story-qa

Scroll the real document; do not drive the scene or change learner storage.
"""
import base64

from test_lab_interactions_browser import enter, main


STATES = [
    ('ready', 'none', '0', '0'),
    ('enter', 'a', '0', '0'),
    ('write', 'a', '3', '0'),
    ('enter', 'b', '3', '0'),
    ('write', 'b', '3', '7'),
    ('done', 'none', '3', '7'),
]
HOST = 'point-call-story.pcs-enhanced'


def traverse(page):
    """Collect viewpoints where the reader can see the stage AND the active text."""
    return page.js("""(async () => {
      const host=document.querySelector('point-call-story.pcs-enhanced');
      const stage=host.querySelector('.pcs-stage'), beats=[...host.querySelectorAll('.pcs-beats li')];
      const track=host.querySelector('.pcs-track');
      const offset=()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
      const go=async y=>{scrollTo({top:y,behavior:'instant'});await offset();};
      const t=track.getBoundingClientRect(), begin=Math.max(0,Math.floor(scrollY+t.top-innerHeight*.57));
      const end=Math.ceil(scrollY+t.bottom-innerHeight*.12);
      await go(begin);
      const choices={}, forward=[], backward=[];
      const record=(arr)=>{
        const i=Number(host.dataset.step);if(i!==arr.at(-1))arr.push(i);
        const b=beats[i].querySelector('h4').getBoundingClientRect(), s=stage.getBoundingClientRect();
        if(s.width<=0 || s.top < -1 || s.bottom>innerHeight+1 || b.top<0 || b.bottom>innerHeight)return;
        const stacked=b.left<s.right && b.right>s.left;
        if(stacked && b.top<s.bottom)return;
        const center=(b.top+b.bottom)/2, line=stacked?(innerHeight+s.bottom)/2:(s.bottom+s.top)/2;
        const score=Math.abs(center-line);
        if(!choices[i]||choices[i].score>score)choices[i]={score,y:scrollY,stageTop:s.top};
      };
      const increment=Math.min(56,innerHeight/12);
      const positions=[];
      for(let y=begin;y<end;y+=increment)positions.push(y);
      positions.push(end);
      for(const y of positions){await go(y);record(forward);}
      for(const y of positions.reverse()){await go(y);record(backward);}
      return {choices,forward,backward};
    })()""")


def snapshot(page):
    return page.js("""(() => {
      const host=document.querySelector('point-call-story.pcs-enhanced'), stage=host.querySelector('.pcs-stage');
      const active=[...host.querySelectorAll('.pcs-beats li')].map((b,i)=>b.getAttribute('aria-current')==='step'?i:-1).filter(i=>i>=0);
      const obj=n=>stage.querySelector('.pcs-object[data-object='+n+'] .pcs-value').textContent.trim();
      const arrows=['a','b'].filter(n=>{
        const path=stage.querySelector('.pcs-to-'+n), css=getComputedStyle(path);
        return css.visibility==='visible' && css.display!=='none' && path.getBoundingClientRect().width>0;
      });
      const r=stage.getBoundingClientRect(), bound=document.documentElement.clientWidth;
      return {step:Number(host.dataset.step),phase:host.dataset.phase,target:host.dataset.target,active,
        a:obj('a'),b:obj('b'),arrows,line:stage.querySelector('.pcs-line').textContent.trim(),
        captionLine:host.querySelector('li[aria-current=step]').dataset.line,
        assignment:stage.querySelector('.pcs-assignment').textContent.trim(),
        argument:stage.querySelector('.pcs-arg').textContent.trim(),label:stage.querySelector('.pcs-this-label').textContent.trim(),
        stageText:stage.textContent,hash:location.hash,
        fits:r.width>0&&r.left>=-1&&r.right<=bound+1&&r.top>=-1&&r.bottom<=innerHeight+1&&
          document.documentElement.scrollWidth<=bound+1};
    })()""")


def run(page, roadmap, width, out):
    page.viewport(width, 800)
    reduced = width == 375
    page.call('Emulation.setEmulatedMedia', {'media': 'screen', 'features': [
        {'name': 'prefers-reduced-motion', 'value': 'reduce' if reduced else 'no-preference'}]})
    page.call('Network.emulateNetworkConditions', {'offline': True, 'latency': 0,
              'downloadThroughput': 0, 'uploadThroughput': 0})
    url = (roadmap / 'cpp_station0_oop_basics.html').as_uri() + '#section=this'
    page.goto(url, f"document.querySelectorAll('{HOST} .pcs-stage').length===1")
    assert page.js("document.querySelectorAll('point-call-story .pcs-beats li').length") == len(STATES)
    assert page.js("document.querySelector('article').dataset.termsScope") == 'this'
    result = traverse(page)
    assert result['forward'] == list(range(6)) and result['backward'] == list(reversed(range(6))), (width, result)
    assert set(result['choices']) == set(map(str, range(6))), ('no joint diagram/text viewpoint', width, result)
    # The same figure should hold its position while the explanatory text advances.
    tops = [result['choices'][str(i)]['stageTop'] for i in range(1,5)]
    assert max(tops) - min(tops) < 2, ('not sticky', width, tops)
    for i, (phase, target, a, b) in enumerate(STATES):
        y = result['choices'][str(i)]['y']
        page.js(f"scrollTo({{top:{y},behavior:'instant'}});new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(()=>r(true))))")
        state = snapshot(page)
        assert state['step'] == i, ('scroll position did not restore the same frame',width,i,y,state,result)
        assert (state['phase'], state['target'], state['a'], state['b']) == (phase, target, a, b), (width,i,state)
        assert state['active'] == [i] and state['arrows'] == ([] if target=='none' else [target]), (width,i,state)
        assert state['line'] == state['captionLine'] and state['line'], (width,i,state)
        assert state['fits'] and state['hash'] == '#section=this', (width,i,state)
        if target != 'none':
            assert f'{target}.setX(' in state['line'], (width,i,state)
            assert state['label'] == 'this' and state['assignment'] == 'this->x = value;', (width,i,state)
            assert state['argument'].endswith('3' if target == 'a' else '7'), (width,i,state)
        if phase == 'done':
            assert '3 7' in state['stageText'] and state['assignment'] == 'return x;', state
        if phase == 'ready':
            assert state['assignment'] == 'int x = 0;', state
        if reduced:
            assert not page.js("document.querySelector('.pcs-stage').getAnimations({subtree:true}).some(a=>a.playState==='running' && a.effect.getTiming().duration>5)")
        if out and i in (1, 2, 3, 5):
            cap=page.call('Page.captureScreenshot', {'format':'png','captureBeyondViewport':False})
            (out / f'this-{width}-{i+1}.png').write_bytes(base64.b64decode(cap['data']))
    enter(page, 'point-call-story .pcs-skip')
    page.wait("document.activeElement.matches('.pcs-after')")
    assert page.js("location.hash") == '#section=this'
    page.js("location.hash='section=why-oop'; true")
    page.wait("document.querySelector('article')?.dataset.termsScope==='why-oop' && !document.querySelector('point-call-story')")
    page.js("location.hash='section=this'; true")
    page.wait(f"document.querySelectorAll('{HOST} .pcs-stage').length===1")
    if width == 320:
        # A short screen must not leave the reader trapped behind a pinned figure.
        page.viewport(640, 360)
        page.wait("getComputedStyle(document.querySelector('.pcs-stage')).position==='static'")
        enter(page, 'point-call-story .pcs-skip')
        page.wait("document.activeElement.matches('.pcs-after')")
        page.call('Emulation.setEmulatedMedia', {'media': 'print'})
        assert page.js("!document.querySelector('.pcs-stage').getClientRects().length && [...document.querySelectorAll('.pcs-beats li')].every(b=>b.getClientRects().length>0)")
    print(f'{width}px: 6 states forward/back, object values, receiver arrow, sticky layout, keyboard skip, return; offline'
          + ('; reduced motion' if reduced else ''), flush=True)


if __name__ == '__main__':
    main(run, 'PASS: station 0 Point::setX story', widths=(1280, 375, 320))
