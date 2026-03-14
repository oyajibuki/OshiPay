function doPost(e) {
    try {
        // 1. パラメータの取得
        var data = JSON.parse(e.postData.contents);
        var email = data.email;
        var license_key = data.license_key;

        // 2. スプレッドシートへ記録 (データベース代わり)
        var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
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
        var adminEmail = Session.getActiveUser().getEmail(); // あなたのGmailアドレス
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

    } catch (error) {
        // エラー時のレスポンス
        return ContentService.createTextOutput(JSON.stringify({
            "status": "error",
            "message": error.toString()
        })).setMimeType(ContentService.MimeType.JSON);
    }
}

function doGet(e) {
    try {
        var license_key = e.parameter.license_key;
        if (!license_key) {
            return ContentService.createTextOutput(JSON.stringify({
                "status": "error",
                "message": "Missing license_key parameter."
            })).setMimeType(ContentService.MimeType.JSON);
        }

        var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
        var data = sheet.getDataRange().getValues();

        // スプレッドシートの全データを走査してキーを検索
        // 1行目はヘッダーなので、i=1から開始
        for (var i = 1; i < data.length; i++) {
            // ライセンスキーはC列(インデックス2)にある想定
            if (data[i][2] === license_key) {
                return ContentService.createTextOutput(JSON.stringify({
                    "status": "success",
                    "valid": true,
                    "email": data[i][1] // メールアドレスはB列(インデックス1)
                })).setMimeType(ContentService.MimeType.JSON);
            }
        }

        // 見つからなかった場合
        return ContentService.createTextOutput(JSON.stringify({
            "status": "success",
            "valid": false
        })).setMimeType(ContentService.MimeType.JSON);

    } catch (error) {
        return ContentService.createTextOutput(JSON.stringify({
            "status": "error",
            "message": error.toString()
        })).setMimeType(ContentService.MimeType.JSON);
    }
}
