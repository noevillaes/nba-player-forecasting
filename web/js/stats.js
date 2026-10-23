// The 16 box-score stats the model forecasts, and the orders they're shown in.

export const STAT_NAME = {
  MIN: "Minutes", PTS: "Points", REB: "Rebounds", OREB: "Off. rebounds", DREB: "Def. rebounds",
  AST: "Assists", STL: "Steals", BLK: "Blocks", TO: "Turnovers", PF: "Fouls", FGM: "FG made",
  FGA: "FG attempted", "3PM": "3P made", "3PA": "3P attempted", FTM: "FT made", FTA: "FT attempted",
};

/** columns of the box score */
export const BOX = ["MIN", "PTS", "REB", "AST", "STL", "BLK", "TO", "FGM", "FGA", "3PM", "FTM"];
/** order of the strips in an opened player */
export const DETAIL_ORDER = ["PTS", "MIN", "REB", "AST", "STL", "BLK", "TO", "FGM", "FGA", "3PM", "3PA",
  "FTM", "FTA", "OREB", "DREB", "PF"];
/** order of the track record table */
export const RECORD_ORDER = ["PTS", "REB", "AST", "MIN", "STL", "BLK", "TO", "3PM", "3PA", "FGM", "FGA",
  "FTM", "FTA", "OREB", "DREB", "PF"];

/** Each player stat is stored as [forecast, q10, q90, last-10 average, actual, abs error, inside 80%]. */
export const unpack = (v) => {
  const [fc, lo, hi, base, real, err, inside] = v;
  return { fc, lo, hi, base, real, err, inside };
};
