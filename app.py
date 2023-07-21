# save this as app.py
import os
import boto3
import json
from krkn_lib_kubernetes import ChaosRunTelemetry
from flask import Flask, Response, request
from typing import Optional

app = Flask(__name__)

request_id_param: str = "request_id"


@app.route("/", methods=['POST'])
def telemetry():
    content_type = request.headers.get('Content-Type')
    if content_type == 'application/json':
        try:
            query_params = request.args
            if request_id_param not in query_params.keys():
                return Response(
                    "[bad request]: missing request_id param",
                    status=400
                )

            folder_name = query_params.get(request_id_param)
            bucket_name = os.getenv("BUCKET_NAME")
            if bucket_name is None:
                return Response("BUCKET_NAME env variable not set", status=500)

            telemetry_data = ChaosRunTelemetry(request.json)
            validation_response = validate_data_model(telemetry_data)
            # if validator returns means that there are validation errors
            if validation_response is not None:
                return validation_response

            s_three = boto3.resource('s3')
            bucket = s_three.Bucket(bucket_name)

            telemetry_str = json.dumps(
                telemetry_data, default=lambda o: o.__dict__, indent=4
            )
            bucket.put_object(
                Key=f"{folder_name}/telemetry.json",
                Body=telemetry_str
            )
            return Response(f"record {folder_name}/telemetry.json created")
        except Exception as e:
            return Response(f"[bad request]: {str(e)}", status=400)
    else:
        return Response("content type not supported", status=415)


@app.route("/prometheus", methods=['POST'])
def prometheus():
    query_params = request.args
    if request_id_param not in query_params.keys():
        return Response(
            "[bad request]: missing request_id param",
            status=400
        )

    folder_name = query_params.get(request_id_param)
    bucket_name = os.getenv("BUCKET_NAME")
    file_stream = request.stream
    s_three = boto3.client('s3')
    s_three.upload_fileobj(file_stream, bucket_name, f"{folder_name}/test_file")
    return Response(f"record {folder_name}/test_file created")

def validate_data_model(model: ChaosRunTelemetry) -> Optional[Response]:
    for scenario in model.scenarios:
        for attr, _ in scenario.__dict__.items():
            if attr != "parametersBase64":
                if getattr(scenario, attr) is None or getattr(scenario, attr) == "":
                    return Response(f"[bad request]: {attr} is null or empty")
    return None
