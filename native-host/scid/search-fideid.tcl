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

# Scid returns the extra PGN tags as one `Tag "value"' line per tag.
proc extraTagValue {extraTags tagName} {
    foreach line [split $extraTags "\n"] {
        set line [string trim $line]
        if {$line eq ""} {
            continue
        }
        if {[regexp {^([A-Za-z0-9_]+)[ \t]+"(.*)"$} $line -> name value]} {
            if {$name eq $tagName} {
                return $value
            }
        }
    }
    return ""
}

if {[llength $argv] != 4} {
    puts stderr "INVALID_ARGUMENTS"
    exit 2
}

lassign $argv databaseBase fideId offset limit
# The identifier is interpolated into a Scid tag pattern, so it stays digits only.
if {![regexp {^[0-9]{1,12}$} $fideId] ||
    ![string is integer -strict $offset] || $offset < 0 ||
    ![string is integer -strict $limit] || $limit < 1 || $limit > 500} {
    puts stderr "INVALID_ARGUMENTS"
    exit 2
}

set baseId 0
set blackFilter ""
try {
    set baseId [sc_base open SCID5 $databaseBase]
    requiredReadOnly $baseId

    # An unquoted, wildcard-free pattern is Scid's complete-value tag match.
    sc_filter reset $baseId dbfilter full
    sc_filter search $baseId dbfilter tags WhiteFideId $fideId

    # The black side is searched separately, then merged without duplicates.
    set blackFilter [sc_filter new $baseId]
    sc_filter reset $baseId $blackFilter full
    sc_filter search $baseId $blackFilter tags BlackFideId $fideId
    sc_filter or $baseId dbfilter $blackFilter
    sc_filter release $baseId $blackFilter
    set blackFilter ""

    set total [sc_filter count $baseId dbfilter]
    set examined 0
    set returned 0

    if {$total > $offset} {
        foreach {index line deleted} \
            [sc_base gameslist $baseId $offset $limit dbfilter "N-"] {
            incr examined
            set gameNumber [lindex [split $index "_"] 0]
            if {![string is integer -strict $gameNumber]} {
                continue
            }
            sc_game load $gameNumber
            set extraTags [sc_game tags get Extra]
            set values [list \
                [sc_game tags get Date] \
                [sc_game tags get Event] \
                [sc_game tags get Round] \
                [sc_game tags get White] \
                [sc_game tags get Black] \
                [sc_game tags get Result] \
                [sc_game tags get WhiteElo] \
                [sc_game tags get BlackElo] \
                [sc_game tags get ECO] \
                [extraTagValue $extraTags WhiteFideId] \
                [extraTagValue $extraTags BlackFideId]]
            set encoded {}
            foreach value $values {
                lappend encoded [encodeField $value]
            }
            puts "GAME\t$gameNumber\t[join $encoded \t]"
            incr returned
        }
    }
    puts "META\t$total\t$returned\t$examined"
} on error {message options} {
    puts stderr $message
    exit 1
} finally {
    if {$blackFilter ne "" && $baseId != 0} {
        catch {sc_filter release $baseId $blackFilter}
    }
    if {$baseId != 0} {
        catch {sc_base close $baseId}
    }
}

exit 0
