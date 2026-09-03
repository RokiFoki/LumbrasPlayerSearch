const NATIVE_HOST = "app.chessgenie.local_games";
const ALLOWED_COMMANDS = new Set([
  "hello",
  "status",
  "configure",
  "searchPlayer",
  "searchFideId",
  "getPgn"
]);

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (
    sender.id !== chrome.runtime.id ||
    message?.type !== "native-request" ||
    !ALLOWED_COMMANDS.has(message.command)
  ) {
    return false;
  }

  chrome.runtime.sendNativeMessage(
    NATIVE_HOST,
    {
      protocolVersion: 1,
      id: crypto.randomUUID(),
      command: message.command,
      payload: message.payload ?? {}
    },
    (response) => {
      if (chrome.runtime.lastError) {
        sendResponse({
          protocolVersion: 1,
          ok: false,
          error: {
            code: "NATIVE_HOST_UNAVAILABLE",
            message: chrome.runtime.lastError.message
          }
        });
        return;
      }

      sendResponse(response);
    }
  );

  return true;
});
