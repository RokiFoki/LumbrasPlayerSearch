proc progressCallBack {args} {
    return 1
}

proc fail {message} {
    puts stderr "error=$message"
    exit 1
}

if {[llength $argv] != 3} {
    fail "usage: query-player.tcl DATABASE_BASE PLAYER_QUERY OUTPUT_PGN"
}

lassign $argv databaseBase playerQuery outputPgn
set baseId 0

try {
    set started [clock milliseconds]
    set baseId [sc_base open SCID5 $databaseBase]
    set opened [clock milliseconds]

    set readOnly [sc_base isReadOnly $baseId]
    if {!$readOnly} {
        fail "database did not open read-only; refusing to continue"
    }

    set gameCount [sc_base numGames $baseId]
    set nameMatches [sc_name match p $playerQuery 10]

    sc_search header -filter RESET -player $playerQuery
    set searched [clock milliseconds]
    set matchedGames [sc_filter count]
    set firstGame [sc_filter first]

    if {$firstGame == 0} {
        fail "no games matched player query '$playerQuery'"
    }

    set pgn [sc_game pgn \
        -base $baseId \
        -gameNumber $firstGame \
        -format plain \
        -tags 1 \
        -comments 1 \
        -variations 1 \
        -width 100]

    set output [open $outputPgn w]
    try {
        puts -nonewline $output $pgn
    } finally {
        close $output
    }

    set finished [clock milliseconds]
    puts "tcl_patchlevel=[info patchlevel]"
    puts "scid_version=[sc_info version]"
    puts "database_base=$databaseBase"
    puts "read_only=$readOnly"
    puts "database_games=$gameCount"
    puts "player_query=$playerQuery"
    puts "name_matches=$nameMatches"
    puts "matched_games=$matchedGames"
    puts "first_game_number=$firstGame"
    puts "output_pgn=$outputPgn"
    puts "open_ms=[expr {$opened - $started}]"
    puts "search_ms=[expr {$searched - $opened}]"
    puts "export_ms=[expr {$finished - $searched}]"
    puts "total_ms=[expr {$finished - $started}]"
} on error {message options} {
    puts stderr "error=$message"
    if {[dict exists $options -errorinfo]} {
        puts stderr [dict get $options -errorinfo]
    }
    exit 1
} finally {
    if {$baseId != 0} {
        catch {sc_base close $baseId}
    }
}

exit 0
