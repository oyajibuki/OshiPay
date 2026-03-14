function doPost(e) {
    try {
        // 1. パラメータの取得
        var data = JSON.parse(e.postData.contents);
        var type = data.type || "license"; // "license" or "access"

        // スプレッドシートの取得
        var ss = SpreadsheetApp.getActiveSpreadsheet();

        // ==========================================
        // アクセスカウンター処理 (type === "access" の場合)
        // ==========================================
        if (type === "access") {
            var accessSheet = ss.getSheetByName("アクセスログ");
            // もし「アクセスログ」というシートが無ければ自動で作成する
            if (!accessSheet) {
                accessSheet = ss.insertSheet("アクセスログ");
                accessSheet.appendRow(["アクセス日時", "IPアドレス", "ユーザーエージェント"]);
            }

            var ip = data.ip || "unknown";
            var ua = data.user_agent || "unknown";

            // ログ行の追加
            accessSheet.appendRow([new Date(), ip, ua]);

            return ContentService.createTextOutput(JSON.stringify({
                "status": "success",
                "message": "Access logged."
            })).setMimeType(ContentService.MimeType.JSON);
        }

        // ==========================================
        // ライセンス発行処理 (type === "license" の場合)
        // ==========================================
        if (type === "license") {
            var email = data.email;
            var license_key = data.license_key;

            // シート1 (標準のシート) を取得
            var sheet = ss.getSheets()[0];
            // ヘッダーがない場合は追加
            if (sheet.getLastRow() === 0) {
                sheet.appendRow(["発行日時", "メールアドレス", "ライセンスキー"]);
            }
            sheet.appendRow([new Date(), email, license_key]);

            // 3. お客様へメール送信
            var subject = "【ClearCut Pro】 ライセンスキーの発行";
            var body =
                "ClearCut Proへのアップグレードありがとうございます。\n\n" +
                "あなたのライセンスキー：\n" +
                license_key + "\n\n" +
                "ClearCutの画面右上「Already have a license? Enter here.」から\n" +
                "このキーを入力すると、機能制限が解除されます。\n\n" +
                "—— ClearCut 運営より\n" +
                "Simple. Fast. Just works.";

            MailApp.sendEmail({
                to: email,
                subject: subject,
                body: body
            });

            // 4. 管理者用（自分宛）の通知メール
            var adminEmail = "oyajibuki@gmail.com";
            var adminSubject = "【管理者通知】ClearCut 新規ライセンス発行";
            var adminBody = "新しいライセンスが発行されました。\n\n" +
                "お客様のメールアドレス： " + email + "\n" +
                "ライセンスキー： " + license_key;

            MailApp.sendEmail({
                to: adminEmail,
                subject: adminSubject,
                body: adminBody
            });

            // 5. 成功レスポンスを返す
            return ContentService.createTextOutput(JSON.stringify({
                "status": "success",
                "message": "Email sent and data saved."
            })).setMimeType(ContentService.MimeType.JSON);
        }

        // 不明なタイプの場合
        return ContentService.createTextOutput(JSON.stringify({
            "status": "error",
            "message": "Unknown event type."
        })).setMimeType(ContentService.MimeType.JSON);

    } catch (error) {
        // エラー時のレスポンス
        return ContentService.createTextOutput(JSON.stringify({
            "status": "error",
            "message": error.toString()
        })).setMimeType(ContentService.MimeType.JSON);
    }
}
