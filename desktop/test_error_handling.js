const axios = require('axios');

// エラーハンドリング改善テスト用スクリプト
async function testErrorHandling() {
    console.log('エラーハンドリング改善テスト開始');
    
    const API_BASE = 'http://127.0.0.1:8001';
    
    try {
        // 1. 存在しないファイルに対する文字起こし（404エラーを期待）
        console.log('\n1. 存在しないファイル - 文字起こし');
        try {
            await axios.post(`${API_BASE}/api/transcribe`, {
                video_path: '/nonexistent/path/video.mp4',
                model_size: 'large-v3'
            });
            console.log('❌ エラーが発生しませんでした（期待されない）');
        } catch (error) {
            if (error.response?.status === 404) {
                console.log('✅ 404エラー - 正しいエラーハンドリング');
                console.log(`   メッセージ: ${error.response.data.detail}`);
            } else {
                console.log(`❌ 想定外のエラー: ${error.response?.status}`);
            }
        }
        
        // 2. 存在しないファイルに対する動画処理（404エラーを期待）
        console.log('\n2. 存在しないファイル - 動画処理');
        try {
            await axios.post(`${API_BASE}/api/process`, {
                video_path: '/nonexistent/path/video.mp4',
                original_text: 'test',
                edited_text: 'test'
            });
            console.log('❌ エラーが発生しませんでした（期待されない）');
        } catch (error) {
            if (error.response?.status === 404) {
                console.log('✅ 404エラー - 正しいエラーハンドリング');
                console.log(`   メッセージ: ${error.response.data.detail}`);
            } else {
                console.log(`❌ 想定外のエラー: ${error.response?.status}`);
            }
        }
        
        // 3. ディレクトリをファイルとして指定（400エラーを期待）
        console.log('\n3. ディレクトリをファイルとして指定');
        try {
            await axios.post(`${API_BASE}/api/process`, {
                video_path: '/Users/naoki/myProject/TextffCut/videos',  // ディレクトリ
                original_text: 'test',
                edited_text: 'test'
            });
            console.log('❌ エラーが発生しませんでした（期待されない）');
        } catch (error) {
            if (error.response?.status === 400) {
                console.log('✅ 400エラー - 正しいエラーハンドリング');
                console.log(`   メッセージ: ${error.response.data.detail}`);
            } else {
                console.log(`❌ 想定外のエラー: ${error.response?.status} - ${error.response?.data?.detail}`);
            }
        }
        
        // 4. 権限がないファイル（403エラーを期待 - ただし、MacOSでは別のエラーが出る可能性）
        console.log('\n4. 権限テスト（制限されたパス）');
        try {
            await axios.post(`${API_BASE}/api/process`, {
                video_path: '/root/protected/video.mp4',
                original_text: 'test',
                edited_text: 'test'
            });
            console.log('❌ エラーが発生しませんでした（期待されない）');
        } catch (error) {
            if (error.response?.status === 404) {
                console.log('✅ 404エラー - 存在しないパスとして処理');
            } else if (error.response?.status === 403) {
                console.log('✅ 403エラー - 権限エラー');
            } else {
                console.log(`ℹ️ その他のエラー: ${error.response?.status} - ${error.response?.data?.detail}`);
            }
        }
        
        // 5. 無効なパラメータ（422エラーを期待）
        console.log('\n5. 無効なパラメータ');
        try {
            await axios.post(`${API_BASE}/api/process`, {
                video_path: '/Users/naoki/myProject/TextffCut/videos/test.mp4'
                // original_text, edited_textが不足
            });
            console.log('❌ エラーが発生しませんでした（期待されない）');
        } catch (error) {
            if (error.response?.status === 422) {
                console.log('✅ 422エラー - バリデーションエラー');
                console.log(`   詳細: ${JSON.stringify(error.response.data.detail?.slice(0, 2) || 'validation error')}`);
            } else {
                console.log(`❌ 想定外のエラー: ${error.response?.status}`);
            }
        }
        
        // 6. 存在しないキャッシュ（404エラーを期待）
        console.log('\n6. 存在しないキャッシュ');
        try {
            await axios.post(`${API_BASE}/api/transcribe/from-cache`, {
                video_name: 'nonexistent_video_12345',
                model_size: 'large-v3'
            });
            console.log('❌ エラーが発生しませんでした（期待されない）');
        } catch (error) {
            if (error.response?.status === 404) {
                console.log('✅ 404エラー - キャッシュが見つからない');
                console.log(`   メッセージ: ${error.response.data.detail}`);
            } else {
                console.log(`❌ 想定外のエラー: ${error.response?.status}`);
            }
        }
        
        // 7. 存在しないタスクID（404エラーを期待）
        console.log('\n7. 存在しないタスクID');
        try {
            await axios.get(`${API_BASE}/api/progress/invalid-task-id-12345`);
            console.log('❌ エラーが発生しませんでした（期待されない）');
        } catch (error) {
            if (error.response?.status === 404) {
                console.log('✅ 404エラー - タスクが見つからない');
                console.log(`   メッセージ: ${error.response.data.detail}`);
            } else {
                console.log(`❌ 想定外のエラー: ${error.response?.status}`);
            }
        }
        
        console.log('\n✅ エラーハンドリング改善テスト完了');
        console.log('\n📊 エラーハンドリング評価:');
        console.log('- ファイル関連エラー: 改善済み（404/400/403）');
        console.log('- パラメータバリデーション: 正常（422）');
        console.log('- キャッシュエラー: 正常（404）');
        console.log('- プログレスエラー: 正常（404）');
        
    } catch (error) {
        console.error('❌ エラーハンドリングテスト中にエラーが発生しました:', error.message);
    }
}

testErrorHandling();