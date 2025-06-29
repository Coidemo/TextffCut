# Phase 6: Presentation層実装計画

## 実装方針

### アーキテクチャ

```
presentation/
├── __init__.py
├── view_models/           # UI用データモデル
│   ├── __init__.py
│   ├── base.py           # 基底ViewModel
│   ├── video_input.py    # 動画入力ViewModel
│   ├── transcription.py  # 文字起こしViewModel
│   ├── text_editing.py   # テキスト編集ViewModel
│   └── export.py         # エクスポートViewModel
├── presenters/            # UIロジック・イベントハンドリング
│   ├── __init__.py
│   ├── base.py           # 基底Presenter
│   ├── video_input.py    # 動画入力Presenter
│   ├── transcription.py  # 文字起こしPresenter
│   ├── text_editing.py   # テキスト編集Presenter
│   └── export.py         # エクスポートPresenter
├── views/                 # Streamlit UI（既存UIのラッパー）
│   ├── __init__.py
│   ├── video_input.py
│   ├── transcription.py
│   ├── text_editing.py
│   └── export.py
└── state/                 # 状態管理
    ├── __init__.py
    └── session_state.py   # Streamlitセッション状態の抽象化
```

## 実装ステップ

### Step 1: 基底クラスの実装

#### 1.1 BaseViewModel
```python
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from abc import ABC, abstractmethod

@dataclass
class BaseViewModel(ABC):
    """ViewModelの基底クラス"""
    _observers: list = field(default_factory=list, init=False)
    
    def subscribe(self, observer):
        """オブザーバーの登録"""
        self._observers.append(observer)
    
    def notify(self):
        """変更通知"""
        for observer in self._observers:
            observer.update(self)
    
    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        pass
```

#### 1.2 BasePresenter
```python
from abc import ABC, abstractmethod
from typing import Generic, TypeVar

TViewModel = TypeVar('TViewModel', bound=BaseViewModel)

class BasePresenter(ABC, Generic[TViewModel]):
    """Presenterの基底クラス"""
    
    def __init__(self, view_model: TViewModel):
        self.view_model = view_model
    
    @abstractmethod
    def initialize(self):
        """初期化処理"""
        pass
```

### Step 2: 動画入力機能の実装（最初の例）

#### 2.1 VideoInputViewModel
```python
@dataclass
class VideoInputViewModel(BaseViewModel):
    """動画入力のViewModel"""
    selected_file: Optional[str] = None
    video_files: list[str] = field(default_factory=list)
    video_info: Optional[Dict[str, Any]] = None
    is_loading: bool = False
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "selected_file": self.selected_file,
            "video_files": self.video_files,
            "video_info": self.video_info,
            "is_loading": self.is_loading,
            "error_message": self.error_message
        }
```

#### 2.2 VideoInputPresenter
```python
from dependency_injector.wiring import Provide, inject

class VideoInputPresenter(BasePresenter[VideoInputViewModel]):
    """動画入力のPresenter"""
    
    @inject
    def __init__(
        self,
        view_model: VideoInputViewModel,
        file_gateway=Provide[ApplicationContainer.gateways.file_gateway],
        video_gateway=Provide[ApplicationContainer.gateways.video_processor_gateway]
    ):
        super().__init__(view_model)
        self.file_gateway = file_gateway
        self.video_gateway = video_gateway
    
    def initialize(self):
        """動画ファイル一覧を初期化"""
        self.refresh_video_list()
    
    def refresh_video_list(self):
        """動画ファイル一覧を更新"""
        try:
            files = self.file_gateway.list_files("videos", ["*.mp4", "*.mov", "*.avi"])
            self.view_model.video_files = sorted(files)
            self.view_model.notify()
        except Exception as e:
            self.view_model.error_message = str(e)
            self.view_model.notify()
    
    def select_video(self, filename: str):
        """動画を選択"""
        self.view_model.selected_file = filename
        self.view_model.is_loading = True
        self.view_model.notify()
        
        try:
            # 動画情報を取得
            info = self.video_gateway.get_video_info(f"videos/{filename}")
            self.view_model.video_info = info
            self.view_model.error_message = None
        except Exception as e:
            self.view_model.error_message = str(e)
            self.view_model.video_info = None
        finally:
            self.view_model.is_loading = False
            self.view_model.notify()
```

### Step 3: セッション状態の抽象化

```python
class SessionStateManager:
    """Streamlitセッション状態の抽象化"""
    
    def __init__(self, session_state):
        self.session_state = session_state
    
    def get_view_model(self, key: str, factory) -> BaseViewModel:
        """ViewModelの取得（なければ作成）"""
        if key not in self.session_state:
            self.session_state[key] = factory()
        return self.session_state[key]
    
    def update_view_model(self, key: str, view_model: BaseViewModel):
        """ViewModelの更新"""
        self.session_state[key] = view_model
```

### Step 4: DIコンテナへの登録

```python
# presentation/di_config.py
from dependency_injector import containers, providers

class PresentationContainer(containers.DeclarativeContainer):
    """Presentation層のDIコンテナ"""
    
    # ゲートウェイ
    gateways = providers.DependenciesContainer()
    
    # ViewModels
    video_input_view_model = providers.Factory(
        VideoInputViewModel
    )
    
    # Presenters
    video_input_presenter = providers.Factory(
        VideoInputPresenter,
        view_model=video_input_view_model,
        file_gateway=gateways.file_gateway,
        video_gateway=gateways.video_processor_gateway
    )
```

## テスト戦略

### 1. ViewModelのテスト
```python
def test_video_input_view_model():
    vm = VideoInputViewModel()
    vm.selected_file = "test.mp4"
    
    assert vm.to_dict()["selected_file"] == "test.mp4"
    assert not vm.is_loading
```

### 2. Presenterのテスト
```python
def test_video_input_presenter():
    # モックゲートウェイ
    mock_file_gateway = Mock()
    mock_file_gateway.list_files.return_value = ["video1.mp4", "video2.mp4"]
    
    vm = VideoInputViewModel()
    presenter = VideoInputPresenter(vm)
    presenter.file_gateway = mock_file_gateway
    
    presenter.refresh_video_list()
    
    assert len(vm.video_files) == 2
    assert vm.video_files[0] == "video1.mp4"
```

## 移行戦略

### Phase 1: 新規実装（影響なし）
- presentation/ディレクトリに新規実装
- 既存コードに影響なし

### Phase 2: 段階的統合
1. main.pyで一部の機能をPresentation層経由に切り替え
2. 動作確認
3. 問題なければ他の機能も順次移行

### Phase 3: 既存UIのリファクタリング
- ui/components.pyの関数をViewに移行
- ビジネスロジックをPresenterに移動

## リスクと対策

1. **Streamlitの制約**
   - リスク: リアクティブな更新が複雑
   - 対策: ViewModelの変更通知メカニズムで対応

2. **パフォーマンス**
   - リスク: 抽象化によるオーバーヘッド
   - 対策: 必要最小限の抽象化に留める

3. **学習コスト**
   - リスク: 新しいパターンの理解が必要
   - 対策: 段階的な導入とドキュメント整備