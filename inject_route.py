content = open('app.py', 'r', encoding='utf-8').read()

route_code = (
    '\n\n@app.route("/bandage-3d")\n'
    '@login_required\n'
    'def bandage_3d_page():\n'
    '    return render_template("bandage_3d.html", user_name=session.get("user_name"))\n'
)

if 'bandage_3d' in content:
    print('Route already present — no change needed.')
else:
    target = '@app.route("/logout")'
    content = content.replace(target, route_code + '\n\n' + target, 1)
    open('app.py', 'w', encoding='utf-8').write(content)
    print('Route inserted successfully.')
