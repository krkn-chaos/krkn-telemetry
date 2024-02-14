# save this as app.py
import os
import boto3
import json
from krkn_lib.models.telemetry import ChaosRunTelemetry
from flask import Flask, Response, request, render_template
from typing import Optional
from datetime import datetime, timedelta

app = Flask(__name__)

telemetry_category: str = "telemetry_category"
request_id_param: str = "request_id"
remote_filename_param: str = "remote_filename"


@app.route("/telemetry", methods=["POST"])
def telemetry():
    content_type = request.headers.get("Content-Type")
    if content_type == "application/json":
        try:
            query_params = request.args
            if request_id_param not in query_params.keys():
                return Response("[bad request]: missing request_id param", status=400)
            category_folder = query_params.get(telemetry_category)
            folder_name = query_params.get(request_id_param)
            if category_folder:
                folder_name = f"{category_folder}/{folder_name}"
            bucket_name = os.getenv("BUCKET_NAME")
            if bucket_name is None:
                return Response("BUCKET_NAME env variable not set", status=500)

            telemetry_data = ChaosRunTelemetry(request.json)
            validation_response = validate_data_model(telemetry_data)
            # if validator returns means that there are validation errors
            if validation_response is not None:
                return validation_response

            s_three = boto3.resource("s3")
            bucket = s_three.Bucket(bucket_name)

            telemetry_str = json.dumps(
                telemetry_data, default=lambda o: o.__dict__, indent=4
            )
            bucket.put_object(Key=f"{folder_name}/telemetry.json", Body=telemetry_str)
            return Response(f"record {folder_name}/telemetry.json created")
        except Exception as e:
            return Response(f"[bad request]: {str(e)}", status=400)
    else:
        return Response("content type not supported", status=415)


@app.route("/presigned-url", methods=["GET"])
def presigned_post():
    query_params = request.args
    if request_id_param not in query_params.keys():
        return Response(
            f"[bad request]: missing {request_id_param} query param", status=400
        )
    if remote_filename_param not in query_params.keys():
        return Response(
            f"[bad request]: missing  {remote_filename_param} query param", status=400
        )

    request_id = query_params[request_id_param]
    if telemetry_category in query_params.keys():
        request_id = f"{query_params[telemetry_category]}/{request_id}"

    remote_filename = query_params[remote_filename_param]
    s_three = boto3.client("s3")

    resp = s_three.generate_presigned_url(
        ClientMethod="put_object",
        Params={
            "Bucket": os.getenv("BUCKET_NAME"),
            "Key": f"{request_id}/{remote_filename}",
        },
        ExpiresIn=int(os.getenv("S3_LINK_EXPIRATION")),
    )
    return Response(resp)


@app.route("/download/", methods=["GET"])
def list_bucket():
    s_three = boto3.client("s3")
    folders = set[str]()
    folder_tuples = []
    items = s_three.list_objects_v2(Bucket=os.getenv("BUCKET_NAME"), Delimiter="/")
    if "CommonPrefixes" not in items.keys():
        return render_template("data_not_found.html")
    for folder in items["CommonPrefixes"]:
        folders.add(folder["Prefix"])
    folders = sorted(folders)
    for folder in folders:
        folder_tuples.append((f"{request.base_url}{folder.replace('/','')}", folder))
    return render_template(
        "telemetry_folders.html",
        folders=folder_tuples,
    )


@app.route("/download/<request_id>", methods=["GET"])
def download(request_id):
    if request_id is None:
        return Response("400", "request_id is missing")
    s_three = boto3.client("s3")
    files = s_three.list_objects_v2(Bucket=os.getenv("BUCKET_NAME"), Prefix=request_id)
    if "Contents" not in files.keys():
        return render_template(
            "telemetry_not_found.html",
            request_id=request_id,
            home_url=f"{request.root_url}download",
        )

    bucket_files = []
    for key in files["Contents"]:
        link = s_three.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": os.getenv("BUCKET_NAME"), "Key": key["Key"]},
            ExpiresIn=int(os.getenv("S3_LINK_EXPIRATION")),
        )
        bucket_files.append(
            (
                link,
                key["Key"].replace(f"{request_id}/", ""),
                key["Size"],
                key["LastModified"],
            )
        )
    expires = datetime.today() + timedelta(
        seconds=float(os.getenv("S3_LINK_EXPIRATION"))
    )

    return render_template(
        "downloads.html",
        files=bucket_files,
        expiration=expires,
        request_id=request_id,
        files_number=len(list(filter(lambda k: "prometheus-" in k[1], bucket_files)))
        - 1,
        home_url=f"{request.root_url}download",
    )


def validate_data_model(model: ChaosRunTelemetry) -> Optional[Response]:
    for scenario in model.scenarios:
        for attr, _ in scenario.__dict__.items():
            if attr != "parametersBase64":
                if getattr(scenario, attr) is None or getattr(scenario, attr) == "":
                    return Response(
                        f"[bad request]: {attr} is null or empty", status=400
                    )
    return None
