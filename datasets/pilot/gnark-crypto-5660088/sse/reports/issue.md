## Description

ScalarMulGLVAndFakeGLV doesn't work for some specific scalar values. It seems scalars of the form `s = order - k` with k " small " makes the Eiseinstein Half GCD hint running into an infinite loop.

While the case scalar = order -1 is covered explicitly in the circuit (otherwise, the hint doesn't converge similarly), it seems order -2, -3, .... (even order -100000000000 and more)) values are causing an issue. No issues found for`scalar < order // 2`

The problem is similar on other GLVAndFakeGLV curves (bn254, bls12-381)

## Steps to Reproduce

Add the following test case to the existing GLV edge case tests:

```go
	order := new(big.Int)
	order.SetString("FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141", 16) // Secp256k1 order
	order_minus_2 := new(big.Int)
	order_minus_2.Sub(order, big.NewInt(2))
	var expected secp256k1.G1Affine
	expected.ScalarMultiplication(&g, order_minus_2)

	witness6 := ScalarMulGLVAndFakeGLVEdgeCasesTest[emulated.Secp256k1Fp, emulated.Secp256k1Fr]{
		S: emulated.ValueOf[emulated.Secp256k1Fr](order_minus_2),
		P: AffinePoint[emulated.Secp256k1Fp]{
			X: emulated.ValueOf[emulated.Secp256k1Fp](g.X),
			Y: emulated.ValueOf[emulated.Secp256k1Fp](g.Y),
		},
		R: AffinePoint[emulated.Secp256k1Fp]{
			X: emulated.ValueOf[emulated.Secp256k1Fp](expected.X),
			Y: emulated.ValueOf[emulated.Secp256k1Fp](expected.Y),
		},
	}
	err = test.IsSolved(&circuit, &witness6, testCurve.ScalarField())
	assert.NoError(err)
```
## Context

## Your Environment

-   gnark version used: MASTER branch
    
-   Operating System and version: