# Servicesパッケージ移行分析

## 現状分析

### 1. アーキテクチャの違い

#### レガシーアーキテクチャ（main_legacy.py）
```
UI → Services → Core（レガシー実装）
```

#### クリーンアーキテクチャ（main.py）
```
UI → Presenter → UseCase → Gateway → Core（レガシー実装）
```

### 2. Servicesパッケージの位置づけ

現在のservicesパッケージは：
- **レガシーアーキテクチャでのみ使用**
- main_legacy.pyから呼び出される
- 直接coreパッケージに依存

新しいクリーンアーキテクチャでは：
- **servicesは使われていない**
- 同等の機能はUseCaseで実装
- Presenter → UseCase → Gatewayの流れ

### 3. 移行の必要性評価

#### 移行不要の理由
1. **既にUseCaseで実装済み**
   - TranscriptionService → TranscribeVideoUseCase
   - VideoProcessingService → 各種動画処理UseCase
   - TextEditingService → TextProcessingUseCase
   - ExportService → 各種エクスポートUseCase

2. **main.pyでは使われていない**
   - 新しいアーキテクチャは完全にUseCase経由
   - servicesへの依存なし

3. **レガシー版のみで使用**
   - main_legacy.pyは移行期間中の互換性維持用
   - 将来的に削除予定

## 結論

### servicesパッケージの移行は不要

理由：
1. **既に移行済み** - UseCaseとして再実装されている
2. **使用されていない** - 新アーキテクチャでは不要
3. **レガシー専用** - main_legacy.pyと共に削除予定

### 推奨アクション

1. **servicesパッケージはそのまま維持**
   - main_legacy.pyが動作する間は必要
   - 移行期間中の互換性維持

2. **将来的に削除**
   - main_legacy.pyの削除時に一緒に削除
   - 完全移行後は不要

3. **新機能はUseCaseで実装**
   - 新しい機能は全てUseCase層で実装
   - servicesには触らない

## 移行ステータス

| レガシーService | 対応するUseCase | ステータス |
|-----------------|-----------------|------------|
| TranscriptionService | TranscribeVideoUseCase, LoadTranscriptionCacheUseCase | ✅ 実装済み |
| VideoProcessingService | RemoveSilenceUseCase, ExtractSegmentsUseCase, CombineSegmentsUseCase | ✅ 実装済み |
| TextEditingService | ProcessTextDifferencesUseCase | ✅ 実装済み |
| ExportService | ExportToFCPXMLUseCase, ExportToSRTUseCase, ExportVideoUseCase | ✅ 実装済み |

## まとめ

servicesパッケージの移行は既に完了しています。新しいクリーンアーキテクチャでは、同等の機能がUseCase層で実装されており、servicesは使用されていません。

今後の作業：
1. ✅ servicesの移行（実は既に完了）
2. ⬜ レガシーコードの削除準備
3. ⬜ main_legacy.pyの削除タイミング決定