"""Turn the app page (template with the data inlined, no html/head/body) into a standalone HTML document.

python -I make_standalone.py <page.html> <out.html>      (engine/build.py calls standalone() directly)
"""
import sys


def standalone(t):
    cut = t.index("</style>") + len("</style>")
    head, body = t[:cut], t[cut:]
    return ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            '<style>:root{color-scheme:light;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}'
            'body{margin:0;font:14px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif}img{max-width:100%}[hidden]{display:none!important}</style>\n'
            + head + '\n</head>\n<body>\n' + body.lstrip("\n") + '\n</body>\n</html>\n')


if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    out = standalone(open(src, encoding="utf-8").read())
    open(dst, "w", encoding="utf-8", newline="\n").write(out)
    print("standalone", dst, len(out.encode()) // 1024, "KB")
