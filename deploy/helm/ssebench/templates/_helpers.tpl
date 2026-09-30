{{/* The name that the chart's objects are prefixed with. */}}
{{- define "ssebench.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 40 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 40 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 40 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end }}

{{- define "ssebench.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{/* Labels of every object. The pods of a component add the selector's, which has the instance. */}}
{{- define "ssebench.labels" -}}
{{ include "ssebench.commonLabels" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "ssebench.commonLabels" -}}
helm.sh/chart: {{ include "ssebench.chart" . }}
app.kubernetes.io/part-of: ssebench
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}

{{/*
The labels that select the pods of one component: litellm, litellm-db, catalog or webui. The name label of
the proxy's pods is the backend's default proxy selector.
*/}}
{{- define "ssebench.selector" -}}
app.kubernetes.io/name: {{ .component }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
{{- end }}

{{/* The image of a component: <registry>/<name>:<tag>, the tag defaulting to image.tag and the chart's appVersion. */}}
{{- define "ssebench.image" -}}
{{- $tag := default (default .root.Chart.AppVersion .root.Values.image.tag) .image.tag -}}
{{- printf "%s/%s:%s" (.root.Values.image.registry | trimSuffix "/") .image.name $tag -}}
{{- end }}

{{- define "ssebench.imagePullSecrets" -}}
{{- with .Values.image.pullSecrets }}
imagePullSecrets:
{{- range . }}
  - name: {{ . }}
{{- end }}
{{- end }}
{{- end }}

{{- define "ssebench.scheduling" -}}
{{- with .Values.nodeSelector }}
nodeSelector: {{- toYaml . | nindent 2 }}
{{- end }}
{{- with .Values.tolerations }}
tolerations: {{- toYaml . | nindent 2 }}
{{- end }}
{{- with .Values.affinity }}
affinity: {{- toYaml . | nindent 2 }}
{{- end }}
{{- end }}

{{/* The Secret with the master key, the database password and the web UI's token. */}}
{{- define "ssebench.authSecret" -}}
{{- default (printf "%s-auth" (include "ssebench.fullname" .)) .Values.auth.existingSecret -}}
{{- end }}

{{- define "ssebench.serviceAccountName" -}}
{{- default (include "ssebench.fullname" .) .Values.serviceAccount.name -}}
{{- end }}

{{/* The namespace of the runs. */}}
{{- define "ssebench.runsNamespace" -}}
{{- default .Release.Namespace .Values.runs.namespace -}}
{{- end }}

{{/* The proxy's Service and the URL that a run's pod reaches it at. */}}
{{- define "ssebench.litellmService" -}}
{{- printf "%s-litellm" (include "ssebench.fullname" .) -}}
{{- end }}

{{- define "ssebench.litellmUrl" -}}
{{- printf "http://%s.%s.svc:4000" (include "ssebench.litellmService" .) .Release.Namespace -}}
{{- end }}

{{- define "ssebench.databaseService" -}}
{{- printf "%s-db" (include "ssebench.litellmService" .) -}}
{{- end }}

{{- define "ssebench.catalogService" -}}
{{- printf "%s-catalog" (include "ssebench.fullname" .) -}}
{{- end }}

{{- define "ssebench.webuiService" -}}
{{- printf "%s-webui" (include "ssebench.fullname" .) -}}
{{- end }}
