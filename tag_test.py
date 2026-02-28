import re

text = '''这样设置，

#eSIM #海外旅行 #旅行攻略 #手机设置 #备用机 海外再无流量焦急，纯干货分享我的亲测心得！
'''

pattern = r'#([^\s#，。！？,。!?"\'\[\]]+)(?:\[话题\]#?)?'
matches = list(re.finditer(pattern, text))
main_content = re.sub(r'\s*' + pattern + r'\s*', ' ', text)
main_content = re.sub(r'\n{3,}', '\n\n', main_content).strip()

print('-- matches --')
print([m.group(0) for m in matches])
print('-- main_content --')
print(repr(main_content))
