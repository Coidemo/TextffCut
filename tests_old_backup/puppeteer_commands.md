# Puppeteer MCP コマンド集

TextffCut E2Eテストで実際に動作したPuppeteerコマンドをまとめています。

## 1. ブラウザ起動とナビゲーション

### アプリケーションを開く
```javascript
// Puppeteer MCPでナビゲート（allowDangerousが必要）
await mcp__puppeteer__puppeteer_navigate({
    url: "http://localhost:8501",
    allowDangerous: true,
    launchOptions: {
        headless: false,
        args: ["--no-sandbox", "--disable-setuid-sandbox"]
    }
});
```

### ページリロード
```javascript
await mcp__puppeteer__puppeteer_evaluate({
    script: "location.reload();"
});
```

## 2. スクリーンショット撮影

### 基本的なスクリーンショット
```javascript
await mcp__puppeteer__puppeteer_screenshot({
    name: "01_home",
    width: 1280,
    height: 800
});
```

### 連番でスクリーンショット
```javascript
const screenshots = [
    "01_home",
    "02_after_update", 
    "03_dropdown_opened",
    "04_scrolled_view",
    "05_dropdown_with_options"
];

for (const name of screenshots) {
    await mcp__puppeteer__puppeteer_screenshot({
        name: name,
        width: 1280,
        height: 800
    });
}
```

## 3. 要素の操作

### ボタンクリック（テキストで検索）
```javascript
await mcp__puppeteer__puppeteer_evaluate({
    script: `
        // 更新ボタンを探してクリック
        const buttons = Array.from(document.querySelectorAll('button'));
        const updateButton = buttons.find(btn => btn.textContent.includes('更新'));
        if (updateButton) {
            updateButton.click();
            'Update button clicked';
        } else {
            'Update button not found';
        }
    `
});
```

### Streamlitのドロップダウン操作
```javascript
await mcp__puppeteer__puppeteer_evaluate({
    script: `
        // Streamlitのdivベースのセレクトボックスを探す
        const selectDivs = document.querySelectorAll('div[data-baseweb="select"]');
        if (selectDivs.length > 0) {
            selectDivs[0].click();
            'Select box clicked';
        } else {
            'No select box found';
        }
    `
});
```

### テキスト入力（Reactコンポーネント対応）
```javascript
await mcp__puppeteer__puppeteer_evaluate({
    script: `
        (() => {
            const input = document.querySelector('input[type="text"]');
            if (input) {
                // Reactのイベントをトリガー
                const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 
                    "value"
                ).set;
                nativeInputValueSetter.call(input, '/path/to/video.mp4');
                
                const ev1 = new Event('input', { bubbles: true });
                input.dispatchEvent(ev1);
                
                const ev2 = new Event('change', { bubbles: true });
                input.dispatchEvent(ev2);
                
                return 'Path entered successfully';
            }
            return 'Input not found';
        })();
    `
});
```

## 4. ページ情報の取得

### ページ内のテキスト確認
```javascript
await mcp__puppeteer__puppeteer_evaluate({
    script: "document.body.innerText.substring(0, 500);"
});
```

### 要素の情報を取得
```javascript
await mcp__puppeteer__puppeteer_evaluate({
    script: `
        // すべての入力要素を確認
        (() => {
            const inputs = document.querySelectorAll('input');
            const result = [];
            inputs.forEach((input, index) => {
                result.push({
                    index: index,
                    type: input.type,
                    placeholder: input.placeholder,
                    value: input.value,
                    visible: input.offsetParent !== null
                });
            });
            return result;
        })();
    `
});
```

### セレクトボックスのオプション取得
```javascript
await mcp__puppeteer__puppeteer_evaluate({
    script: `
        (() => {
            const selects = document.querySelectorAll('select');
            const result = [];
            selects.forEach((select, index) => {
                const options = Array.from(select.options).map(opt => opt.text);
                result.push({
                    index: index,
                    options: options,
                    visible: select.offsetParent !== null
                });
            });
            return result;
        })();
    `
});
```

## 5. スクロール操作

### ページスクロール
```javascript
await mcp__puppeteer__puppeteer_evaluate({
    script: "window.scrollTo(0, 500);"
});
```

## 6. 待機処理

### 要素が表示されるまで待機（JavaScript版）
```javascript
await mcp__puppeteer__puppeteer_evaluate({
    script: `
        // 要素が表示されるまで待つ関数
        const waitForElement = (selector, timeout = 5000) => {
            return new Promise((resolve, reject) => {
                const startTime = Date.now();
                const checkInterval = setInterval(() => {
                    const element = document.querySelector(selector);
                    if (element && element.offsetParent !== null) {
                        clearInterval(checkInterval);
                        resolve(element);
                    } else if (Date.now() - startTime > timeout) {
                        clearInterval(checkInterval);
                        reject(new Error('Timeout waiting for element'));
                    }
                }, 100);
            });
        };
        
        // 使用例
        waitForElement('button:contains("更新")')
            .then(() => 'Element found')
            .catch(() => 'Element not found');
    `
});
```

## 7. デバッグ用コマンド

### コンソールログを確認
```javascript
await mcp__puppeteer__puppeteer_evaluate({
    script: "console.log('Debug message'); 'Check console output';"
});
```

### 現在のURLを取得
```javascript
await mcp__puppeteer__puppeteer_evaluate({
    script: "window.location.href"
});
```

## 使用例：完全なテストフロー

```javascript
// 1. アプリを開く
await mcp__puppeteer__puppeteer_navigate({
    url: "http://localhost:8501",
    allowDangerous: true,
    launchOptions: { headless: false }
});

// 2. 初期画面のスクリーンショット
await mcp__puppeteer__puppeteer_screenshot({
    name: "01_initial",
    width: 1280,
    height: 800
});

// 3. 更新ボタンをクリック
await mcp__puppeteer__puppeteer_evaluate({
    script: `
        const buttons = Array.from(document.querySelectorAll('button'));
        const updateButton = buttons.find(btn => btn.textContent.includes('更新'));
        if (updateButton) updateButton.click();
    `
});

// 4. 少し待機
await new Promise(resolve => setTimeout(resolve, 2000));

// 5. 更新後のスクリーンショット
await mcp__puppeteer__puppeteer_screenshot({
    name: "02_updated",
    width: 1280,
    height: 800
});
```

## 注意事項

1. **allowDangerous: true** - セキュリティ警告を回避するために必要
2. **Streamlit特有のセレクタ** - `div[data-baseweb="select"]`などStreamlit固有の属性を使用
3. **非同期処理** - Streamlitは動的にUIを更新するため、適切な待機が必要
4. **イベントトリガー** - Reactコンポーネントには適切なイベント発火が必要

## トラブルシューティング

### "Maximum call stack size exceeded" エラー
- 複雑なDOM操作で発生することがある
- より単純な操作に分割する

### "Execution context was destroyed" エラー
- ページがリロードされた後に発生
- 再度navigateコマンドを実行する

### 要素が見つからない
- Streamlitは動的にDOMを生成するため、待機処理を追加
- より具体的なセレクタを使用