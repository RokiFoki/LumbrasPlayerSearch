proc progressCallBack {args} {
    return 1
}

proc encodeField {value} {
    return [binary encode base64 -maxlen 0 [encoding convertto utf-8 $value]]
}

proc requiredReadOnly {baseId} {
    if {![sc_base isReadOnly $baseId]} {
        error "READ_ONLY_REQUIRED"
    }
}

if {[llength $argv] != 4} {
    puts stderr "INVALID_ARGUMENTS"
    exit 2
}

lassign $argv databaseBase playerQuery offset limit
if {![string is integer -strict $offset] || $offset < 0 ||
    ![string is integer -strict $limit] || $limit < 1 || $limit > 500} {
    puts stderr "INVALID_ARGUMENTS"
    exit 2
}

set baseId 0
try {
    set baseId [sc_base open SCID5 $databaseBase]
    requiredReadOnly $baseId

    set nameMatches [sc_name match p $playerQuery 25]
    set selectedPlayer ""
    foreach {frequency name} $nameMatches {
        puts "CANDIDATE\t$frequency\t[encodeField $name]"
        if {[string equal -nocase [string trim $name] [string trim $playerQuery]]} {
            set selectedPlayer $name
        }
    }

    if {$selectedPlayer eq ""} {
        puts "META\t0\t0\t[encodeField ""]"
    } else {
        # Surrounding quotes request Scid's exact, case-sensitive name match.
        set exactPlayer "\"$selectedPlayer\""
        sc_search header -filter RESET -player $exactPlayer
        set total [sc_filter count]
        set gameNumber [sc_filter last]
        set skipped 0
        while {$gameNumber != 0 && $skipped < $offset} {
            set gameNumber [sc_filter previous]
            incr skipped
        }

        set returned 0
        while {$gameNumber != 0 && $returned < $limit} {
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
            incr returned
            set gameNumber [sc_filter previous]
        }
        puts "META\t$total\t$returned\t[encodeField $selectedPlayer]"
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
