package main

import (
	"fmt"
	"math/big"
	"os"
	"time"

	"github.com/Consensys/gnark-crypto/field/eisenstein"
)

func main() {
	a0, _ := new(big.Int).SetString("64502973549206556628585045361533709077", 10)
	a1, _ := new(big.Int).SetString("-303414439467246543595250775667605759171", 10)
	c0, _ := new(big.Int).SetString("-432420386565659656852420866390673177323", 10)
	c1, _ := new(big.Int).SetString("238911465918039986966665730306072050094", 10)

	a := eisenstein.ComplexNumber{A0: a0, A1: a1}
	c := eisenstein.ComplexNumber{A0: c0, A1: c1}

	doneCh := make(chan struct{})

	go func() {
		eisenstein.HalfGCD(&a, &c)
		close(doneCh)
	}()

	select {
	case <-doneCh:
		fmt.Println("Success: HalfGCD converged.")
		os.Exit(0)
	case <-time.After(2 * time.Second):
		fmt.Println("VULNERABILITY REPRODUCED: HalfGCD timed out (Infinite Loop detected)")
		os.Exit(1)
	}
}