import importlib.util
mods = ['pandas', 'numpy', 'streamlit', 'plotly', 'openai', 'sklearn', 'flask', 'requests', 'sqlalchemy']
for m in mods:
    spec = importlib.util.find_spec(m)
    if spec:
        try:
            mod = importlib.import_module(m)
            v = getattr(mod, '__version__', '?')
            print(f'{m}: OK ({v})')
        except Exception as e:
            print(f'{m}: IMPORT-ERROR ({e})')
    else:
        print(f'{m}: MISSING')
