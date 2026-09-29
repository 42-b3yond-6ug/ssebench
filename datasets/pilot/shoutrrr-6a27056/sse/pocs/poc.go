package main

import (
	"strings"

	"github.com/containrrr/shoutrrr/pkg/types"
	"github.com/containrrr/shoutrrr/pkg/util"
)

func main() {
	// "Sending exactly 2000, 4000 or 6000 characters to Discord panics"
	limits := types.MessageLimit{
		ChunkSize:      2000,
		TotalChunkSize: 6000,
		ChunkCount:     10,
	}
	
	const maxSearchRunes = 100
	payload := strings.Repeat("A", 2000)
	util.PartitionMessage(payload, limits, maxSearchRunes)
}