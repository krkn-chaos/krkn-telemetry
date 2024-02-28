import os
import re
import json
from flask import Flask, Response, request, render_template, jsonify, redirect, url_for
from typing import Optional
import boto3
from krkn_lib.models.telemetry import ChaosRunTelemetry, S3BucketObject


app = Flask(__name__)

request_id_param: str = "request_id"
telemetry_group_param: str = "telemetry_group"
remote_filename_param: str = "remote_filename"


@app.route("/", methods=["GET"])
def root():
    return redirect(url_for("get_groups", group_id=None, run_id=None), code=302)


## TELEMETRY JSON API
@app.route("/telemetry", methods=["POST"])
def telemetry():
    content_type = request.headers.get("Content-Type")
    if content_type == "application/json":
        try:
            query_params = request.args
            if request_id_param not in query_params.keys():
                return Response("[bad request]: missing request_id param", status=400)
            if telemetry_group_param not in query_params.keys():
                return Response(
                    "[bad request]: missing telemetry_group param", status=400
                )
            folder_name = query_params.get(request_id_param)
            folder_name = f"{query_params.get(telemetry_group_param)}/{folder_name}"

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


## UPLOAD URL API
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


## DOWNLOAD URL API
@app.route("/download-url/<filename>", methods=["GET"])
@app.route("/download-url/<group_id>/<filename>", methods=["GET"])
@app.route("/download-url/<group_id>/<run_id>/<filename>", methods=["GET"])
def get_download_link(filename, group_id=None, run_id=None):
    try:
        file_path = filename
        if group_id:
            file_path = f"{group_id}/{filename}"
        if run_id:
            file_path = f"{group_id}/{run_id}/{filename}"
        s_three = boto3.client("s3")
        link = s_three.generate_presigned_url(
            ClientMethod="get_object",
            Params={
                "Bucket": os.getenv("BUCKET_NAME"),
                "Key": file_path,
            },
            ExpiresIn=int(os.getenv("S3_LINK_EXPIRATION")),
        )
    except Exception as e:
        return Response("400", f"error fetching download url: {e}")
    return jsonify({"download_link": link})


## BUCKET NAVIGATION API
@app.route("/navigate")
@app.route("/navigate/<group>")
@app.route("/navigate/<group>/<run>")
def get_objects(group=None, run=None):
    s3 = boto3.client("s3")
    s3_paginator = s3.get_paginator("list_objects_v2")
    delimiter = "/"
    prefix = ""
    if group:
        prefix = f"{group}/"
    if run:
        prefix = f"{group}/{run}/"
    s3_iterator = s3_paginator.paginate(
        Bucket=os.getenv("BUCKET_NAME"),
        Delimiter=delimiter,
        Prefix=prefix,
        PaginationConfig={"MaxItems": 13},
    )
    objects = []
    for key_data in s3_iterator:
        keys = key_data.keys()
        if "Contents" in keys:
            for file in key_data["Contents"]:
                s3_object = S3BucketObject(
                    path=re.sub(r"^.+/(.+)$", r"\1", file["Key"]),
                    type="file",
                    size=file["Size"],
                    modified=file["LastModified"],
                )
                objects.append(s3_object)
        if "CommonPrefixes" in keys:
            for s3_folder in key_data["CommonPrefixes"]:
                s3_object = S3BucketObject(
                    path=re.sub(r"^.+/(.+)$", r"\1", s3_folder["Prefix"]),
                    type="folder",
                    size=0,
                    modified="",
                )
                objects.append(s3_object)
    return jsonify(objects)


## TELEMETRY FILE MANAGER UI
@app.route("/files/<group_id>/<run_id>/", methods=["GET"])
@app.route("/files/<group_id>/", methods=["GET"])
@app.route("/files/", methods=["GET"])
def get_groups(group_id=None, run_id=None):
    if not group_id and not run_id:
        return render_template(
            "telemetry_files.html",
            navigation_api=f"{request.root_url}navigate",
            download_url_api=f"{request.root_url}download-url",
            link_url=request.base_url,
            request_path=request.path,
            run_id=run_id,
            group_id=group_id,
        )
    if group_id and not run_id:
        return render_template(
            "telemetry_files.html",
            navigation_api=f"{request.root_url}navigate/{group_id}",
            download_url_api=f"{request.root_url}download-url",
            link_url=request.base_url,
            request_path=request.path,
            run_id=run_id,
            group_id=group_id,
        )

    return render_template(
        "telemetry_files.html",
        navigation_api=f"{request.root_url}navigate/{group_id}/{run_id}",
        download_url_api=f"{request.root_url}download-url",
        link_url=request.base_url,
        request_path=request.path,
        run_id=run_id,
        group_id=group_id,
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
