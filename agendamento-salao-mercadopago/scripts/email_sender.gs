function doPost(event) {
  try {
    const data = JSON.parse(event.postData.contents || "{}");
    const expectedSecret = PropertiesService.getScriptProperties().getProperty("EMAIL_WEBHOOK_SECRET") || "";

    if (!constantTimeEquals(String(data.secret || ""), expectedSecret)) {
      return jsonResponse({ ok: false });
    }
    if (!data.to || !data.subject || !data.text || !data.html) {
      return jsonResponse({ ok: false });
    }

    MailApp.sendEmail(data.to, data.subject, data.text, {
      htmlBody: data.html,
      name: "Agendamento do Salão",
    });
    return jsonResponse({ ok: true });
  } catch (error) {
    console.error("Falha ao enviar e-mail de confirmação.", error);
    return jsonResponse({ ok: false });
  }
}

function authorizeEmailSending() {
  return MailApp.getRemainingDailyQuota();
}

function constantTimeEquals(left, right) {
  if (!left || !right || left.length !== right.length) return false;
  let difference = 0;
  for (let index = 0; index < left.length; index += 1) {
    difference |= left.charCodeAt(index) ^ right.charCodeAt(index);
  }
  return difference === 0;
}

function jsonResponse(value) {
  return ContentService
    .createTextOutput(JSON.stringify(value))
    .setMimeType(ContentService.MimeType.JSON);
}
