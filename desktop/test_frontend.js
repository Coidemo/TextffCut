const axios = require('axios');

// フロントエンド機能テスト用スクリプト
async function testFrontendFeatures() {
    console.log('フロントエンド機能テスト開始');
    
    try {
        // 1. React アプリの基本ロード確認
        console.log('\n1. Reactアプリ基本ロード確認');
        const response = await axios.get('http://localhost:3000');
        if (response.status === 200 && response.data.includes('TextffCut Desktop')) {
            console.log('✅ Reactアプリは正常にロードされています');
        } else {
            console.log('❌ Reactアプリのロードに問題があります');
        }
        
        // 2. API接続テスト（設定取得）
        console.log('\n2. API接続テスト');
        const settingsResponse = await axios.get('http://127.0.0.1:8001/api/settings');
        if (settingsResponse.status === 200) {
            console.log('✅ APIとの接続は正常です');
            console.log(`利用可能なWhisperモデル: ${settingsResponse.data.whisper_models.join(', ')}`);
        } else {
            console.log('❌ API接続に問題があります');
        }
        
        // 3. キャッシュ機能テスト
        console.log('\n3. キャッシュ機能テスト');
        const cacheResponse = await axios.get('http://127.0.0.1:8001/api/transcribe/cache-status/test/large-v3');
        if (cacheResponse.status === 200) {
            console.log('✅ キャッシュ機能は正常です');
            console.log(`キャッシュ状態: ${cacheResponse.data.has_cache ? 'あり' : 'なし'}`);
        } else {
            console.log('❌ キャッシュ機能に問題があります');
        }
        
        // 4. エラーハンドリングテスト
        console.log('\n4. エラーハンドリングテスト');
        try {
            await axios.post('http://127.0.0.1:8001/api/transcribe', {
                video_path: '/nonexistent/file.mp4',
                model_size: 'large-v3'
            });
            console.log('❌ エラーハンドリングが動作していません');
        } catch (error) {
            if (error.response && error.response.status === 404) {
                console.log('✅ エラーハンドリングは正常に動作しています');
            } else {
                console.log('❌ 想定外のエラーが発生しました');
            }
        }
        
        // 5. プログレス機能テスト
        console.log('\n5. プログレス機能テスト');
        try {
            await axios.get('http://127.0.0.1:8001/api/progress/nonexistent-task');
            console.log('❌ プログレス機能のエラーハンドリングが動作していません');
        } catch (error) {
            if (error.response && error.response.status === 404) {
                console.log('✅ プログレス機能のエラーハンドリングは正常です');
            } else {
                console.log('❌ プログレス機能で想定外のエラーが発生しました');
            }
        }
        
        console.log('\n✅ フロントエンド機能テスト完了');
        
    } catch (error) {
        console.error('❌ テスト実行中にエラーが発生しました:', error.message);
    }
}

testFrontendFeatures();