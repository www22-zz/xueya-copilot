"""Compile every Markdown example and compare core algorithms with independent oracles.

No credentials or model providers are loaded. Generated binaries stay in the
ignored test-results directory. The document, not a second code copy, is tested.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MATERIAL = ROOT/'materials/stack-queue/栈与队列知识库.md'

COMMON = r'''
#include <algorithm>
#include <deque>
#include <functional>
#include <random>
#include <string>
#include <vector>
'''

EXTRA = {
    'C02': r'''
    ArrayStack q; std::vector<int> model;
    for (int i=0;i<6000;++i) {
        if (rng()%2 && model.size()<3) { int x=int(rng()%100);q.push(x);model.push_back(x); }
        else if (!model.empty()) { assert(q.pop()==model.back());model.pop_back(); }
        assert(q.size()==int(model.size()) && q.empty()==model.empty());
        assert(q.full()==(model.size()==3));
        if (!model.empty()) assert(q.peek()==model.back());
    }''',
    'C03': r'''
    LinkedStack q; std::vector<int> model;
    for(int i=0;i<6000;++i) {
        if(rng()%2 || model.empty()) {int x=int(rng()%200)-100;q.push(x);model.push_back(x);}
        else {assert(q.pop()==model.back());model.pop_back();}
        assert(q.empty()==model.empty());
        if(!model.empty()) assert(q.peek()==model.back());
    }''',
    'C05': r'''
    for(int n=2;n<=30;++n) {
        CircularQueue q(n); std::deque<int> model;
        for(int i=0;i<3000;++i) {
            if(rng()%2 && int(model.size())<n-1) {int x=int(rng()%1000);q.enqueue(x);model.push_back(x);}
            else if(!model.empty()) {assert(q.dequeue()==model.front());model.pop_front();}
            assert(q.size()==int(model.size()) && q.capacity()==n-1);
            assert(q.empty()==model.empty() && q.full()==(int(model.size())==n-1));
            if(!model.empty()) assert(q.head()==model.front());
        }
    }
    for(int n : {0,1,100001}) {
        bool bad=false;try {CircularQueue q(n);} catch(const std::invalid_argument&) {bad=true;}
        assert(bad);
    }''',
    'C06': r'''
    LinkedQueue q; std::deque<int> model;
    for(int i=0;i<6000;++i) {
        if(rng()%2 || model.empty()) {int x=int(rng()%200)-100;q.enqueue(x);model.push_back(x);}
        else {assert(q.dequeue()==model.front());model.pop_front();}
        assert(q.empty()==model.empty());
        if(!model.empty()) assert(q.head()==model.front());
    }''',
    'C07': r'''
    // Recursive grammar recognition, independent of the iterative stack algorithm.
    std::function<bool(const std::string&,std::size_t&,char)> parse;
    parse=[&](const std::string& s,std::size_t& i,char close) {
        while(i<s.size()) {
            char c=s[i++];
            if(c==')'||c==']') return c==close;
            if(c=='('||c=='[') {if(!parse(s,i,c=='('?')':']')) return false;}
        }
        return close=='\0';
    };
    const std::string alphabet="()[]";
    for(int len=0;len<=7;++len) {
        unsigned total=1u<<(2*len);
        for(unsigned bits=0;bits<total;++bits) {
            std::string s;unsigned v=bits;
            for(int j=0;j<len;++j) {s+=alphabet[v%4];v/=4;}
            std::size_t pos=0;bool expected=parse(s,pos,'\0')&&pos==s.size();
            assert(balanced(s)==expected);
        }
    }''',
    'C08': r'''
    for(int i=0;i<2000;++i) {
        long long a=int(rng()%2001)-1000,b=int(rng()%2001)-1000;
        std::string prefix=std::to_string(a)+" "+std::to_string(b)+" ";
        assert(postfix(prefix+"+")==a+b && postfix(prefix+"-")==a-b);
        assert(postfix(prefix+"*")==a*b);
        if(b) assert(postfix(prefix+"/")==a/b);
    }
    for(const char* s : {"", "1 2", "1 2 %", "12x", "2 0 /", "1000000001", "1000000000 1000000000 *"}) {
        bool bad=false;try {postfix(s);}catch(const std::exception&){bad=true;}assert(bad);
    }''',
    'C09': r'''
    for(int n=1;n<=14;++n) for(int trial=0;trial<15;++trial) {
        std::vector<std::vector<int>> graph(n),d(n,std::vector<int>(n,999));
        for(int i=0;i<n;++i) d[i][i]=0;
        for(int i=0;i<n;++i) for(int j=0;j<n;++j) if(rng()%4==0) {
            graph[i].push_back(j);d[i][j]=std::min(d[i][j],1);
        }
        // Floyd-Warshall is the oracle, not another BFS.
        for(int k=0;k<n;++k)for(int i=0;i<n;++i)for(int j=0;j<n;++j)
            d[i][j]=std::min(d[i][j],d[i][k]+d[k][j]);
        for(int s=0;s<n;++s) {
            auto actual=bfs(graph,s);
            for(int v=0;v<n;++v) assert(actual[v]==(d[s][v]==999?-1:d[s][v]));
        }
    }''',
    'C10': r'''
    TwoStackQueue q;std::deque<int> model;
    for(int i=0;i<6000;++i) {
        if(rng()%2 || model.empty()) {int x=int(rng()%200)-100;q.enqueue(x);model.push_back(x);}
        else {assert(q.dequeue()==model.front());model.pop_front();}
        assert(q.empty()==model.empty());
        if(!model.empty()) assert(q.head()==model.front());
    }''',
    'C11': r'''
    MinStack q;std::vector<int> model;
    for(int i=0;i<6000;++i) {
        if(rng()%2 || model.empty()) {int x=int(rng()%7)-3;q.push(x);model.push_back(x);}
        else {assert(q.pop()==model.back());model.pop_back();}
        assert(q.empty()==model.empty());
        if(!model.empty()) assert(q.minValue()==*std::min_element(model.begin(),model.end()));
    }''',
    'C12': r'''
    for(int n=0;n<=60;++n)for(int trial=0;trial<30;++trial) {
        std::vector<int> a(n),expected(n,-1);for(int& x:a)x=int(rng()%11)-5;
        for(int i=0;i<n;++i)for(int j=i+1;j<n;++j)if(a[j]>a[i]){expected[i]=j;break;}
        assert(nextGreaterIndex(a)==expected);
    }''',
    'C13': r'''
    for(int n=1;n<=50;++n)for(int trial=0;trial<15;++trial) {
        std::vector<int> a(n);for(int& x:a)x=int(rng()%11)-5;
        for(int k=1;k<=n;++k) {
            std::vector<int> expected;
            for(int i=0;i+k<=n;++i)expected.push_back(*std::max_element(a.begin()+i,a.begin()+i+k));
            assert(windowMax(a,k)==expected);
        }
    }''',
}


def examples(text):
    rows = re.findall(r'^### (C\d{2}) [^\n]+\n\n```cpp\n(.*?)\n```', text, re.M | re.S)
    assert [key for key, _ in rows] == [f'C{i:02}' for i in range(1, 14)]
    assert len(re.findall(r'^```cpp$', text, re.M)) == len(rows)
    return rows


def verify(compiler, output):
    output.mkdir(parents=True, exist_ok=True)
    text = MATERIAL.read_text(encoding='utf-8')
    programs = examples(text)

    def one(row):
        key, code = row
        assert code.count('int main()') == 1
        source = output/(key+'.cpp')
        executable = output/(key+'.exe')
        extended = code.replace('int main()', 'void example_main()', 1)
        extended += COMMON+'\nint main() { example_main(); std::mt19937 rng(20261030);\n'
        extended += EXTRA.get(key, '(void)rng;')+'\n}\n'
        source.write_text(extended, encoding='utf-8')
        built = subprocess.run([compiler, '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', '-pedantic',
                                '-D_GLIBCXX_ASSERTIONS', source.name, '-o', executable.name], cwd=output,
                               capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)
        (output/(key+'-compile.log')).write_text(built.stdout+built.stderr, encoding='utf-8')
        if built.returncode:
            return {'id': key, 'passed': False, 'stage': 'compile', 'code': built.returncode}
        ran = subprocess.run([str(executable)], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
        (output/(key+'-run.log')).write_text(ran.stdout+ran.stderr, encoding='utf-8')
        return {'id': key, 'passed': ran.returncode == 0, 'stage': 'run', 'code': ran.returncode,
                'independentOracle': key in EXTRA}

    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(one, programs))
    report = {'materialSha256': hashlib.sha256(MATERIAL.read_bytes()).hexdigest(), 'compiler': compiler,
              'cppStandard': 'C++17', 'examples': len(rows), 'passed': sum(r['passed'] for r in rows),
              'modelRequests': 0, 'rows': rows}
    (output.parent/'code-validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', default=shutil.which('g++'))
    parser.add_argument('--output', type=Path, default=ROOT/'test-results/stack-queue-md/cpp')
    args = parser.parse_args()
    if not args.compiler:
        raise SystemExit('A C++17 compiler is required; examples were not verified.')
    result = verify(args.compiler, args.output.resolve())
    print(json.dumps({key: result[key] for key in ('examples', 'passed', 'modelRequests')}))
    if result['passed'] != result['examples']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
