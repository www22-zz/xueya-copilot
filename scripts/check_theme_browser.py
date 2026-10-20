"""Read-only live browser audit of both themes, page text and keyboard controls."""
import argparse
import json
from pathlib import Path
import tempfile
from .check_learning_browser import Browser

CONTRAST = r"""(()=>{
const rgb=s=>{const m=s.match(/[\d.]+/g);return m?m.map(Number):[0,0,0,0];};
const over=(f,b)=>{const a=f[3]??1;return [0,1,2].map(i=>f[i]*a+b[i]*(1-a));};
const lum=c=>{const v=c.map(x=>{x/=255;return x<=.04045?x/12.92:((x+.055)/1.055)**2.4;});return .2126*v[0]+.7152*v[1]+.0722*v[2];};
const results=[];
for(const el of document.body.querySelectorAll('*')){
 if(el.closest('[aria-hidden=true],script,style,svg,canvas')||['INPUT','TEXTAREA','SELECT','OPTION'].includes(el.tagName))continue;
 let closed=false;for(let p=el.parentElement;p;p=p.parentElement)if(p.tagName==='DETAILS'&&!p.open&&!p.querySelector(':scope>summary')?.contains(el)){closed=true;break;}if(closed)continue;
 const text=[...el.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent).join('').trim();
 const r=el.getBoundingClientRect(),style=getComputedStyle(el);if(!text||r.width<1||r.height<1||style.visibility!=='visible')continue;
 let chain=[],opacity=1;for(let p=el;p;p=p.parentElement){chain.unshift(p);opacity*=Number(getComputedStyle(p).opacity);}
 if(opacity<.9)continue;
 let bg=document.documentElement.dataset.theme==='dark'?[17,20,28]:[237,242,251];
 for(const p of chain)bg=over(rgb(getComputedStyle(p).backgroundColor),bg);
 const fg=over(rgb(style.color),bg),a=lum(fg),b=lum(bg),ratio=(Math.max(a,b)+.05)/(Math.min(a,b)+.05);
 const large=parseFloat(style.fontSize)>=24||(parseFloat(style.fontSize)>=18.66&&Number(style.fontWeight)>=700),required=large?3:4.5;
 if(ratio<required-.02)results.push({text:text.slice(0,45),tag:el.tagName,classes:el.className,parent:el.parentElement?.className,ratio:Math.round(ratio*100)/100,color:style.color,bg:bg.map(Math.round),required});
}return results.sort((a,b)=>a.ratio-b.ratio);})()"""


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',default='http://127.0.0.1:4173')
    parser.add_argument('--credentials',default='.xueya-data/团队登录信息.json')
    args=parser.parse_args()
    output=Path('test-results/theme-audit');output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='xueya-theme-') as temp:
        browser=Browser(Path(temp))
        reports={}
        try:
            browser.call('Emulation.setDeviceMetricsOverride',width=1440,height=1000,deviceScaleFactor=1,mobile=False)
            browser.call('Emulation.setEmulatedMedia',features=[{'name':'prefers-reduced-motion','value':'no-preference'}])
            browser.call('Page.navigate',url=args.base_url+'/#space/overview')
            browser.wait('!!window.XueyaPreferences && (!!document.querySelector("#accountLoginDialog")?.open || !!document.querySelector("#workspaceMore"))')
            if browser.evaluate('!!document.querySelector("#accountLoginDialog")?.open'):
                c=json.loads(Path(args.credentials).read_text(encoding='utf-8'))
                browser.fill('[data-account-action=login] [name=username]',c['username'])
                browser.fill('[data-account-action=login] [name=password]',c['password'])
                browser.click('[data-account-action=login] button')
            browser.wait('!!document.querySelector("#workspaceMore")')
            for theme in ('light','dark'):
                browser.evaluate('window.XueyaPreferences.applyTheme('+json.dumps(theme)+')')
                for view in ('home','overview','chat','library','cards','practice','memory','chapters','plan','graph'):
                    if view=='home':
                        browser.evaluate('location.hash="home"')
                        browser.wait('!document.querySelector("#homePage").hidden')
                        browser.wait('[...document.querySelectorAll("#homePage .hero-enter,.knowledge-universe")].every(el=>Number(getComputedStyle(el).opacity)>.99) && document.querySelector("#knowledgeCanvas").getBoundingClientRect().width>10')
                    else:browser.route(view)
                    browser.screenshot(output/(theme+'-'+view+'.png'))
                    reports[theme+'-'+view]=browser.evaluate(CONTRAST)
                browser.click('#appSettingsButton')
                browser.click('[data-settings-tab=general]')
                browser.screenshot(output/(theme+'-settings.png'))
                reports[theme+'-settings']=browser.evaluate(CONTRAST)
                browser.click('[data-settings-close]')
            browser.evaluate('location.hash="home"')
            browser.wait('!document.querySelector("#homePage").hidden')
            browser.call('Input.dispatchMouseEvent',type='mouseMoved',x=300,y=350)
            browser.wait('document.body.classList.contains("custom-cursor")')
            assert browser.evaluate('getComputedStyle(document.querySelector(".cursor-ring")).color === "rgb(227, 237, 255)"')
            browser.call('Input.dispatchMouseEvent',type='mouseMoved',x=700,y=350)
            assert browser.evaluate('(()=>{const ring=new DOMMatrixReadOnly(getComputedStyle(document.querySelector(".cursor-ring")).transform);return Math.hypot(ring.m41-700,ring.m42-350)<=10.5;})()')
            browser.screenshot(output/'dark-cursor.png')
            assert browser.evaluate('!document.querySelector("#workspaceMore [data-view=media]")')
            browser.call('Emulation.setDeviceMetricsOverride',width=390,height=844,deviceScaleFactor=1,mobile=True)
            for theme in ('light','dark'):
                browser.evaluate('window.XueyaPreferences.applyTheme('+json.dumps(theme)+')')
                browser.screenshot(output/(theme+'-home-mobile.png'))
                assert browser.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
            assert not browser.errors,browser.errors
            (output/'report.json').write_text(json.dumps({'paidApiCalls':0,'runtimeErrors':browser.errors,'contrast':reports},ensure_ascii=False,indent=2),encoding='utf-8')
            for page,issues in reports.items():
                print(page,len(issues),json.dumps(issues[:5],ensure_ascii=False))
        finally:browser.close()


if __name__=='__main__':main()
