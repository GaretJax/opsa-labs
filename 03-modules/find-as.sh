#!/bin/bash

function get_one_ip() {
	dig +noall +answer $1 A | head -1 | awk '{print $5}'
}

function get_as() {
	whois $1 | grep OriginAS | awk '{print $2}'
}

get_as $(get_one_ip $1)
