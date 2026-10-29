"""Compare whole-journal aggregation and indexed seeks in Chromium.

Synthetic data only. The baseline reconstructs the preceding room.js snapshot
algorithm. Index construction is timed separately; seek checksums must agree.
"""
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from chaosfolk import engine


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=int, default=100000)
    parser.add_argument("--seeks", type=int, default=200)
    args = parser.parse_args()
    if args.events < 1 or args.seeks < 1:
        parser.error("events and seeks must be positive")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page()
            page.add_script_tag(content=(Path(engine.__file__).parent / "templates/playback.js").read_text(encoding="utf-8"))
            result = page.evaluate("""({count, seeks})=>{
                const events=Array.from({length:count},(_,n)=>({h:`h${n%12}`,n,t:n*100,
                    action:n%71===0?'done':n%23===0?'flag':'click',gravite:'blocking',
                    capture:n%7===0?`shot-${n}.png`:null}));
                const findings=Array.from({length:100},(_,n)=>({evenements:[{h:`h${n%12}`,n}]}));
                const points=Array.from({length:seeks},(_,i)=>(i*7919%count)*100);
                const started=performance.now();
                const index=buildPlaybackIndex(events,{timed:true,start:0,findings,
                    validCapture:Boolean,blocking:x=>x==='blocking'});
                const construction=performance.now()-started;
                function baseline(at){
                    const shown=events.filter(e=>e.t<=at), groups=new Map();
                    for(const e of shown){if(!groups.has(e.h))groups.set(e.h,[]);groups.get(e.h).push(e);}
                    const seen=new Set(shown.map(e=>`${e.h}/${e.n}`));
                    let checksum=shown.length+shown.filter(e=>!['look','think','flag','giveup','done'].includes(e.action)).length
                        +shown.filter(e=>e.action==='flag').length+new Set(shown.filter(e=>e.action==='done').map(e=>e.h)).size
                        +findings.filter(f=>f.evenements.some(e=>seen.has(`${e.h}/${e.n}`))).length;
                    for(const group of groups.values())checksum+=(group.at(-1)?.n||0)+(group.findLast(e=>e.capture)?.n||0)
                        +group.some(e=>e.action==='flag'&&e.gravite==='blocking');
                    return checksum;
                }
                function indexed(at){const s=index.snapshot(at);let checksum=s.count+s.actions+s.flags+s.finished+s.found;
                    for(const u of s.users.values())checksum+=(u.last?.n||0)+(u.shot?.n||0)+u.blocking;return checksum;}
                for(const at of points)if(baseline(at)!==indexed(at))throw Error('Snapshot mismatch');
                function measure(fn){const samples=[];for(let r=0;r<3;r++){let checksum=0;const start=performance.now();
                    for(const at of points)checksum+=fn(at);samples.push({ms:performance.now()-start,checksum});}
                    samples.sort((a,b)=>a.ms-b.ms);return samples[1];}
                return {events:count,seeks,repeats:3,index_build_ms:construction,baseline:measure(baseline),indexed:measure(indexed)};
            }""", {"count": args.events, "seeks": args.seeks})
            assert result["baseline"]["checksum"] == result["indexed"]["checksum"]
            result["browser"] = browser.version
            result["scope"] = "Synthetic seek aggregation; excludes DOM rendering, file loading and model costs."
            print(json.dumps(result, indent=2))
        finally:
            browser.close()


if __name__ == "__main__":
    main()
