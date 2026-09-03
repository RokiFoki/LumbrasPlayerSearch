// Classifies the single search field as a player name or a FIDE ID and
// supplies the matching status messages. Loaded before popup.js; it has no
// DOM or Chrome dependencies so the same file runs in the test suite.
const ChessGenieQuery = (() => {
  const MAX_FIDE_ID_DIGITS = 12;
  const MAX_PLAYER_LENGTH = 200;
  // ASCII digits only: other numerals fall back to a name search.
  const FIDE_ID_PATTERN = /^[0-9]+$/;

  function classify(rawValue) {
    const value = typeof rawValue === "string" ? rawValue.trim() : "";
    if (!value) {
      return { kind: "empty" };
    }
    if (FIDE_ID_PATTERN.test(value)) {
      const fideId = value.replace(/^0+/, "");
      if (value.length > MAX_FIDE_ID_DIGITS || !fideId) {
        return { kind: "invalid", reason: "fideId" };
      }
      return { kind: "fideId", fideId };
    }
    if (value.length > MAX_PLAYER_LENGTH) {
      return { kind: "invalid", reason: "player" };
    }
    return { kind: "player", player: value };
  }

  function label(query) {
    return query.kind === "fideId" ? `FIDE ID ${query.fideId}` : query.player;
  }

  function validationMessage(query) {
    if (query.kind === "invalid" && query.reason === "fideId") {
      return `Enter a valid FIDE ID of up to ${MAX_FIDE_ID_DIGITS} digits.`;
    }
    if (query.kind === "invalid") {
      return `Enter a player name of up to ${MAX_PLAYER_LENGTH} characters.`;
    }
    return "Enter a player name or FIDE ID.";
  }

  function searchingMessage(query) {
    if (query.kind === "fideId") {
      return "Searching the local database by FIDE ID. This can take longer than a name search…";
    }
    return "Searching the local database…";
  }

  function notFoundMessage(query) {
    if (query.kind === "fideId") {
      return `No games were found for FIDE ID ${query.fideId}.`;
    }
    return "No matching player name was found.";
  }

  return {
    MAX_FIDE_ID_DIGITS,
    MAX_PLAYER_LENGTH,
    classify,
    label,
    validationMessage,
    searchingMessage,
    notFoundMessage
  };
})();
