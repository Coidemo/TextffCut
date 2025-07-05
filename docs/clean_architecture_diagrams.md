# TextffCut アーキテクチャ図集

## 1. DIコンテナの依存関係図

### 1.1 バランスの取れたコンテナ構造

```mermaid
graph TB
    subgraph "ApplicationContainer（全体管理）"
        AC[ApplicationContainer]
        
        subgraph "設定"
            CONFIG[Config]
            KEYS[SessionKeys]
        end
        
        subgraph "GatewayContainer（接続管理）"
            GW[GatewayContainer]
            FG[FileGateway<br/>新規]
            TPG[TextProcessorGateway<br/>既存活用]
            WG[WhisperXGateway<br/>既存活用]
            FFG[FFmpegGateway<br/>既存活用]
            SDG[SilenceDetectionGateway<br/>既存活用]
            FCPG[FCPXMLExportGateway<br/>既存活用]
            EDLG[EDLExportGateway<br/>既存活用]
            SRTG[SRTExportGateway<br/>新規]
        end
        
        subgraph "UseCaseContainer（業務処理）"
            UC[UseCaseContainer]
            TUC[TranscribeVideoUseCase]
            TEU[TextEditUseCase]
            SDU[SilenceDetectionUseCase]
            EUC[ExportUseCase]
        end
        
        subgraph "PresentationContainer（画面）"
            PC[PresentationContainer]
            SM[SessionManager]
            VM[ViewModels]
            PR[Presenters]
            VW[Views]
        end
    end
    
    %% 依存関係
    AC --> CONFIG
    AC --> KEYS
    SM --> KEYS
    
    TPG --> CONFIG
    WG --> CONFIG
    FFG --> CONFIG
    SDG --> CONFIG
    FCPG --> CONFIG
    EDLG --> CONFIG
    
    UC --> GW
    TUC --> WG
    TEU --> TPG
    SDU --> SDG
    EUC --> FCPG
    EUC --> EDLG
    EUC --> SRTG
    EUC --> FFG
    
    PC --> UC
    PC --> SM
    PR --> VM
    PR --> UC
    PR --> SM
    VW --> PR
    
    style FG fill:#90EE90
    style SRTG fill:#90EE90
    style TPG fill:#FFB6C1
    style WG fill:#FFB6C1
    style FFG fill:#FFB6C1
    style SDG fill:#FFB6C1
    style FCPG fill:#FFB6C1
    style EDLG fill:#FFB6C1
```

### 1.2 データフローと依存性注入の関係

```mermaid
sequenceDiagram
    participant User as ユーザー
    participant View as 画面
    participant Presenter as 画面制御係
    participant UseCase as 業務処理
    participant Gateway as 接続部品
    participant External as 外部システム
    
    Note over View,External: 起動時：DIコンテナがすべての部品を組み立て
    
    User->>View: ボタンクリック
    View->>Presenter: イベント通知
    Presenter->>UseCase: 処理依頼
    UseCase->>Gateway: データ要求
    Gateway->>External: API呼び出し
    External-->>Gateway: 結果返却
    Gateway-->>UseCase: データ返却
    UseCase-->>Presenter: 処理結果
    Presenter->>View: 画面更新
    View-->>User: 結果表示
```

## 2. エラー処理フロー

### 2.1 エラーの伝播と変換

```mermaid
graph LR
    subgraph "外部システム層"
        EXT[外部エラー<br/>ConnectionError等]
    end
    
    subgraph "Infrastructure層"
        GW[Gateway Adapter]
        ET[Error Transformer]
    end
    
    subgraph "Domain層"
        DE[ドメインエラー<br/>NetworkError等]
    end
    
    subgraph "Application層"
        UC[UseCase]
        AE[アプリケーションエラー]
    end
    
    subgraph "Presentation層"
        EH[ErrorHandler]
        MSG[ユーザーメッセージ]
    end
    
    EXT -->|catch| GW
    GW --> ET
    ET -->|変換| DE
    DE -->|throw| UC
    UC -->|catch & wrap| AE
    AE --> EH
    EH -->|変換| MSG
```

### 2.2 エラーメッセージの変換例

```
技術的エラー → ユーザー向けメッセージ

ConnectionError 
  ↓
"ネットワーク接続を確認してください"

FileNotFoundError
  ↓
"指定されたファイルが見つかりません"

PermissionError
  ↓
"ファイルへのアクセス権限がありません"

TimeoutError
  ↓
"処理がタイムアウトしました。もう一度お試しください"
```

## 3. 簡素化されたシステム構成

### 3.1 バランスの取れたデータフロー

```mermaid
graph TB
    subgraph "新システム（実用的）"
        V[View]
        P[Presenter]
        UC[UseCase]
        SM[SessionManager<br/>改善版]
    end
    
    subgraph "ゲートウェイ"
        FG[FileGateway<br/>新規実装]
        TPG[TextProcessorGateway<br/>既存活用]
        WG[WhisperXGateway<br/>既存活用]
        FFG[FFmpegGateway<br/>既存活用]
        SDG[SilenceDetectionGateway<br/>既存活用]
        FCPG[FCPXMLExportGateway<br/>既存活用]
        EDLG[EDLExportGateway<br/>既存活用]
        SRTG[SRTExportGateway<br/>新規実装]
    end
    
    subgraph "外部システム"
        FS[ファイルシステム]
        TP[テキスト処理]
        WX[WhisperX]
        FF[FFmpeg]
        SD[無音検出]
        FE[フォーマット処理]
    end
    
    V --> P
    P --> UC
    P --> SM
    UC --> FG
    UC --> TPG
    UC --> WG
    UC --> FFG
    UC --> SDG
    UC --> FCPG
    UC --> EDLG
    UC --> SRTG
    
    FG --> FS
    TPG --> TP
    WG --> WX
    FFG --> FF
    SDG --> SD
    FCPG --> FE
    EDLG --> FE
    SRTG --> FS
    
    style FG fill:#90EE90
    style SRTG fill:#90EE90
    style TPG fill:#FFB6C1
    style WG fill:#FFB6C1
    style FFG fill:#FFB6C1
    style SDG fill:#FFB6C1
    style FCPG fill:#FFB6C1
    style EDLG fill:#FFB6C1
```

### 3.2 戦略的な既存コード活用

```
既存活用（7つ）:
- WhisperX連携: 複雑なAPI連携
- FFmpeg操作: 動画処理の核心
- 無音検出: 複雑なアルゴリズム
- テキスト処理: 細かいノウハウ
- FCPXMLエクスポート: 複雑なフォーマット
- EDLエクスポート: 業界標準フォーマット

新規実装（2つ）:
- ファイル操作: シンプルなため
- SRTエクスポート: シンプルなテキスト形式
- UI/画面: 完全刷新
```

## 4. パフォーマンス最適化の可視化

### 4.1 Singleton vs Factory

```mermaid
graph LR
    subgraph "Singleton（共有インスタンス）"
        S1[初回作成]
        S2[2回目以降]
        SI[同じインスタンス]
        
        S1 -->|作成| SI
        S2 -->|参照| SI
    end
    
    subgraph "Factory（都度作成）"
        F1[1回目]
        F2[2回目]
        FI1[インスタンス1]
        FI2[インスタンス2]
        
        F1 -->|作成| FI1
        F2 -->|作成| FI2
    end
```

### 4.2 遅延初期化のタイミング

```mermaid
sequenceDiagram
    participant App as アプリケーション
    participant GW as Gateway
    participant Model as 重いリソース
    
    App->>GW: 作成
    Note right of GW: モデルはまだ読み込まない
    
    App->>GW: 他の処理...
    
    App->>GW: transcribe()呼び出し
    GW->>GW: モデルが必要？
    GW->>Model: 初回のみ読み込み
    Model-->>GW: モデル準備完了
    GW-->>App: 処理結果
    
    App->>GW: 2回目のtranscribe()
    Note right of GW: 既に読み込み済み
    GW-->>App: 処理結果
```

## 5. 簡素化前後の比較

### 5.1 バランスの取れたアプローチ

```mermaid
graph LR
    subgraph "Before（複雑）"
        B1[レガシー互換]
        B2[データ変換]
        B3[並行稼働]
        B4[ServiceLayer]
        B5[過度な抽象化]
    end
    
    subgraph "After（実用的）"
        A1[戦略的な既存活用]
        A2[直接的な実装]
        A3[単一システム]
        A4[技術的負債管理]
    end
    
    B1 -.-> A1
    B2 -.-> A2
    B3 -.-> A3
    B4 -.削除.-> X1[×]
    B5 -.簡素化.-> A2
    
    style A1 fill:#90EE90
    style A2 fill:#90EE90
    style A3 fill:#90EE90
    style A4 fill:#87CEEB
    style X1 fill:#FF6B6B
```

### 5.2 現実的な開発効率

```
最適化された作業:
- 既存コードの活用: +20%（実績ある部分）
- 段階的リリース: +10%（早期フィードバック）
- 技術的負債管理: +5%（長期保守性）

結果:
- 開発期間: 3週間 → 5週間（現実的）
- リスク: 低減（段階的実装）
- 品質: 向上（十分なテスト）
```

## 6. 実装ロードマップ

### 6.1 フェーズ別実装スケジュール

```mermaid
gantt
    title TextffCutクリーンアーキテクチャ移行スケジュール
    dateFormat  YYYY-MM-DD
    section 基盤構築
    DIコンテナ設定     :2025-02-03, 3d
    基本層構造         :3d
    エラーハンドリング     :2d
    
    section 文字起こし
    WhisperX Gateway    :2025-02-10, 2d
    Transcription MVP   :3d
    パフォーマンステスト   :2d
    
    section テキスト編集
    TextProcessor Gateway :2025-02-17, 2d
    Text Edit MVP       :3d
    統合テスト         :2d
    
    section エクスポート
    Silence Detection   :2025-02-24, 2d
    FCPXML Export      :2d
    EDL/SRT Export     :3d
    動作確認          :3d
    
    section 統合
    全機能テスト       :2025-03-03, 3d
    パフォーマンス最適化  :2d
    リリース準備       :2d
```

### 6.2 マイルストーンと成果物

| フェーズ | マイルストーン | 成果物 | Go/No-Go基準 |
|---------|---------------|---------|---------------|
| Phase 1 | 基盤完成 | DIコンテナ動作 | テスト通過率 > 90% |
| Phase 2 | 文字起こし動作 | 90分動画処理 | 10分以内で完了 |
| Phase 3 | テキスト編集完成 | 差分検出正確 | 精度 > 95% |
| Phase 4 | エクスポート完成 | 各形式出力 | 互換性確認 |
| Phase 5 | リリース準備 | 完全動作 | ユーザーテスト合格 |

作成日: 2025-01-01  
更新日: 2025-01-30  
バージョン: 2.1（現実的な調整版）