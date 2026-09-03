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
if {[llength $gameNumbers] < 1 || [llength $gameNumbers] > 1000} {
    puts stderr "INVALID_ARGUMENTS"
    exit 2
}

set baseId 0
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
        sc_game load $gameNumber
        set values [list \
            [sc_game tags get Date] \
            [sc_game tags get Event] \
            [sc_game tags get Round] \
            [sc_game tags get White] \
            [sc_game tags get Black] \
            [sc_game tags get Result] \
            [sc_game tags get WhiteElo] \
            [sc_game tags get BlackElo] \
            [sc_game tags get ECO]]
        set encoded {}
        foreach value $values {
            lappend encoded [encodeField $value]
        }
        puts "GAME\t$gameNumber\t[join $encoded \t]"
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
