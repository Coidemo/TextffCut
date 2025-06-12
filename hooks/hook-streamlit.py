"""
PyInstaller Hook for Streamlit
Streamlitのメタデータと必要なファイルを含める
"""

from PyInstaller.utils.hooks import copy_metadata, collect_all

# Streamlitのメタデータをコピー
datas = copy_metadata('streamlit')

# Streamlitの全てのデータを収集
tmp_ret = collect_all('streamlit')
datas += tmp_ret[0]
binaries = tmp_ret[1]
hiddenimports = tmp_ret[2]

# 追加の隠しインポート
hiddenimports += [
    'streamlit.runtime.scriptrunner.magic_funcs',
    'streamlit.runtime.scriptrunner.script_runner',
    'streamlit.runtime.state',
    'streamlit.runtime.stats',
    'streamlit.runtime.uploaded_file_manager',
    'streamlit.web.server.server',
    'streamlit.web.server.websocket_headers',
    'streamlit.delta_generator',
    'streamlit.type_util',
    'streamlit.watcher',
    'streamlit.hello',
    'altair',
    'pandas',
    'numpy',
    'pyarrow',
    'toml',
    'validators',
    'watchdog',
    'click',
    'tornado',
    'blinker',
    'cachetools',
    'gitpython',
    'pydeck',
    'pympler',
    'rich',
    'tzlocal',
]