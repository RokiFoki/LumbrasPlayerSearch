proc progressCallBack {args} {
    return 1
}

proc encodeField {value} {
    return [binary encode base64 -maxlen 0 [encoding convertto utf-8 $value]]
}

if {[llength $argv] != 2} {
    puts stderr "INVALID_ARGUMENTS"
    exit 2
}

lassign $argv databaseBase gameNumberCsv
set gameNumbers [split $gameNumberCsv ","]
set baseId 0
set totalBytes 0

try {
    set baseId [sc_base open SCID5 $databaseBase]
    if {![sc_base isReadOnly $baseId]} {
        error "READ_ONLY_REQUIRED"
    }
    set databaseGames [sc_base numGames $baseId]

    foreach gameNumber $gameNumbers {
        if {![string is integer -strict $gameNumber] ||
            $gameNumber < 1 || $gameNumber > $databaseGames} {
            error "INVALID_GAME_NUMBER"
        }
        set pgn [sc_game pgn \
            -base $baseId \
            -gameNumber $gameNumber \
            -format plain \
            -tags 1 \
            -comments 1 \
            -variations 1 \
            -width 100]
        set pgnBytes [string length [encoding convertto utf-8 $pgn]]
        if {$pgnBytes > 500000} {
            error "PGN_TOO_LARGE"
        }
        incr totalBytes $pgnBytes
        if {$totalBytes > 20000000} {
            error "EXPORT_TOO_LARGE"
        }
        puts "PGN\t$gameNumber\t[encodeField $pgn]"
    }
} on error {message options} {
    puts stderr $message
    exit 1
} finally {
    if {$baseId != 0} {
        catch {sc_base close $baseId}
    }
}

exit 0
