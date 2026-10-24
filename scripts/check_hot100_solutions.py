"""Compile all C++/Java solutions and exercise new Python algorithms with structural/edge checks."""
import concurrent.futures
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import typing
from backend.xueya.practice_bank import questions


class ListNode:
    def __init__(self, val=0, next=None):
        self.val, self.next = val, next


class TreeNode:
    def __init__(self, val=0, left=None, right=None):
        self.val, self.left, self.right = val, left, right


class Node:
    def __init__(self, val=0):
        self.val, self.next, self.random = val, None, None


def chain(values):
    head = None
    for value in reversed(values):
        head = ListNode(value, head)
    return head


def values(head):
    result = []
    while head:
        result.append(head.val)
        head = head.next
        assert len(result) < 100, 'unexpected cycle'
    return result


def inorder(root):
    return inorder(root.left) + [root.val] + inorder(root.right) if root else []


def main():
    hot = [q for q in questions() if q['category'] == 'hot100']
    cases = 0
    for q in hot:
        scope = {**vars(typing),'ListNode': ListNode, 'TreeNode': TreeNode, 'Node': Node}
        exec(q['solutions']['python'], scope)
        if not q['id'].startswith('lc-'):
            continue
        number = q['leetcodeNumber']
        solution = scope['Solution']() if 'Solution' in scope else None
        if number == 141:
            assert not solution.hasCycle(None)
            h = chain([1, 1, 1]); assert not solution.hasCycle(h)
            h.next.next.next = h.next; assert solution.hasCycle(h)
        elif number == 21:
            assert values(solution.mergeTwoLists(chain([1,2,4]),chain([1,3,4]))) == [1,1,2,3,4,4]
            assert values(solution.mergeTwoLists(None,chain([1]))) == [1]
            assert solution.mergeTwoLists(None,None) is None
        elif number == 24:
            for a,b in [([],[]),([1],[1]),([1,2,3],[2,1,3])]:
                assert values(solution.swapPairs(chain(a))) == b
        elif number == 138:
            a,b = Node(1),Node(2); a.next=b; a.random=b; b.random=b
            copy = solution.copyRandomList(a)
            assert copy is not a and copy.next is not b and copy.val==1 and copy.next.val==2
            assert copy.random is copy.next and copy.next.random is copy.next
            assert a.next is b and a.random is b and solution.copyRandomList(None) is None
        elif number == 101:
            assert solution.isSymmetric(TreeNode(1,TreeNode(2),TreeNode(2)))
            assert not solution.isSymmetric(TreeNode(1,TreeNode(2,None,TreeNode(3)),TreeNode(2,None,TreeNode(3))))
            assert solution.isSymmetric(None)
        elif number == 543:
            assert solution.diameterOfBinaryTree(TreeNode(1,TreeNode(2,TreeNode(4),TreeNode(5)),TreeNode(3)))==3
            assert solution.diameterOfBinaryTree(TreeNode(1))==0
            assert solution.diameterOfBinaryTree(None)==0
        elif number == 108:
            for a in [[],[1],[-10,-3,0,5,9]]:
                root=solution.sortedArrayToBST(a); assert inorder(root)==a
                def height(n):
                    if not n:return 0
                    l,r=height(n.left),height(n.right);assert abs(l-r)<=1;return 1+max(l,r)
                height(root)
        elif number == 114:
            root=TreeNode(1,TreeNode(2,TreeNode(3),TreeNode(4)),TreeNode(5,None,TreeNode(6)))
            solution.flatten(root); result=[]
            while root:
                assert root.left is None;result.append(root.val);root=root.right
            assert result==[1,2,3,4,5,6]
            assert solution.flatten(None) is None
        elif number == 105:
            assert inorder(solution.buildTree([3,9,20,15,7],[9,3,15,20,7]))==[9,3,15,20,7]
            assert solution.buildTree([],[]) is None
            assert solution.buildTree([1],[1]).val==1
        elif number == 437:
            root=TreeNode(10,TreeNode(5,TreeNode(3,TreeNode(3),TreeNode(-2)),TreeNode(2,None,TreeNode(1))),TreeNode(-3,None,TreeNode(11)))
            assert solution.pathSum(root,8)==3
            assert solution.pathSum(TreeNode(0,TreeNode(0),TreeNode(0)),0)==5
            assert solution.pathSum(None,0)==0
        elif number == 240:
            assert solution.searchMatrix([[1,4,7],[2,5,8],[3,6,9]],6)
            assert not solution.searchMatrix([[1,4],[2,5]],3)
            assert not solution.searchMatrix([],0)
        elif number == 208:
            trie=scope['Trie']();trie.insert('apple');assert trie.search('apple') and not trie.search('app')
            assert trie.startsWith('app');trie.insert('app');assert trie.search('app')
            assert not trie.startsWith('az')
        elif number == 739:
            assert solution.dailyTemperatures([73,74,75,71,69,72,76,73])==[1,1,4,2,1,1,0,0]
            assert solution.dailyTemperatures([30,30])==[0,0]
            assert solution.dailyTemperatures([100,90,80])==[0,0,0]
        elif number == 84:
            assert solution.largestRectangleArea([2,1,5,6,2,3])==10
            assert solution.largestRectangleArea([2,2])==4
            assert solution.largestRectangleArea([0])==0
        elif number == 5:
            assert solution.longestPalindrome('babad') in ('bab','aba')
            assert solution.longestPalindrome('cbbd')=='bb'
            assert solution.longestPalindrome('a')=='a'
        elif number == 17:
            assert solution.letterCombinations('')==[]
            assert set(solution.letterCombinations('23'))=={'ad','ae','af','bd','be','bf','cd','ce','cf'}
            assert len(solution.letterCombinations('79'))==16
        elif number == 39:
            assert sorted(solution.combinationSum([2,3,6,7],7))==[[2,2,3],[7]]
            assert solution.combinationSum([2],1)==[]
            assert solution.combinationSum([2],4)==[[2,2]]
        elif number == 22:
            assert len(solution.generateParenthesis(3))==5
            assert solution.generateParenthesis(1)==['()']
            assert len(set(solution.generateParenthesis(4)))==14
        elif number == 131:
            assert sorted(solution.partition('aab'))==[['a','a','b'],['aa','b']]
            assert solution.partition('a')==[['a']]
            assert len(solution.partition('aaaa'))==8
        else:
            raise AssertionError(number)
        cases += 1
    cpp = shutil.which('g++') or 'C:/MinGW_c23/mingw64/bin/g++.exe'
    javac = shutil.which('javac') or 'C:/Program Files/Common Files/Oracle/Java/javapath/javac.exe'
    cpp_stub='''#include <bits/stdc++.h>
using namespace std;
struct ListNode {int val;ListNode* next;ListNode(int v=0,ListNode* n=nullptr):val(v),next(n){}};
struct TreeNode {int val;TreeNode *left,*right;TreeNode(int v=0,TreeNode* l=nullptr,TreeNode* r=nullptr):val(v),left(l),right(r){}};
class Node {public:int val;Node *next=nullptr,*random=nullptr;Node(int v):val(v){}};
'''
    java_stub='''class ListNode {int val;ListNode next;ListNode(int v){val=v;}ListNode(int v,ListNode n){val=v;next=n;}}
class TreeNode {int val;TreeNode left,right;TreeNode(int v){val=v;}TreeNode(int v,TreeNode l,TreeNode r){val=v;left=l;right=r;}}
class Node {int val;Node next,random;Node(int v){val=v;}}
'''
    with tempfile.TemporaryDirectory(prefix='hot100-compile-',ignore_cleanup_errors=True) as directory:
        root=Path(directory);files=[]
        for i,q in enumerate(hot):
            cp=root/f'q{i}.cpp';cp.write_text(cpp_stub+q['solutions']['cpp'],encoding='utf-8')
            package=root/f'q{i}';package.mkdir();jp=package/'Solution.java'
            jp.write_text(f'package q{i};\nimport java.util.*;\n'+q['solutions']['java']+'\n'+java_stub,encoding='utf-8');files.append((q['id'],cp,jp))
        def compile_cpp(item):
            q,cp,_=item;result=subprocess.run([cpp,'-std=c++17','-fsyntax-only',str(cp)],capture_output=True,text=True,encoding='utf-8',errors='replace')
            assert result.returncode==0,(q,result.stderr)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(compile_cpp,files))
        result=subprocess.run([javac,'-encoding','UTF-8',*[str(j) for _,_,j in files]],capture_output=True,text=True,encoding='utf-8',errors='replace')
        assert result.returncode==0,result.stderr
    report={'cpp_compiled':100,'java_compiled':100,'python_new_algorithms_structurally_exercised':cases}
    output=Path('test-results/practice-requirements');output.mkdir(parents=True,exist_ok=True)
    (output/'solutions.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(report)


if __name__=='__main__':
    main()
