# Copyright (c) 2026, Kaviya and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from collections import defaultdict


def execute(filters=None):

    columns = getcolumns()
    data = get_data(filters)

    chart = get_chart(data)

    report_summary = get_report_summary(data)

    return columns, data, None, chart, report_summary


def getcolumns():

    columns = [
        {
            "label": _("Technician"),
            "fieldname": "technician",
            "fieldtype": "Link",
            "options": "Technician",
            "width": 180,
        },
        {
            "label": _("Total Jobs"),
            "fieldname": "total_jobs",
            "fieldtype": "Int",
            "width": 120,
        },
        {
            "label": _("Completed"),
            "fieldname": "completed",
            "fieldtype": "Int",
            "width": 120,
        },
        {
            "label": _("Avg Turnaround Days"),
            "fieldname": "avg_turnaround_days",
            "fieldtype": "Float",
            "width": 170,
        },
        {
            "label": _("Revenue"),
            "fieldname": "revenue",
            "fieldtype": "Currency",
            "width": 140,
        },
        {
            "label": _("Completion Rate %"),
            "fieldname": "completion_rate",
            "fieldtype": "Percent",
            "width": 150,
            "color":["green,<=,70","red,>,70"],
        },
    ]

    # Dynamic Device Type Columns
    for dt in frappe.get_list("Device Type", fields=["name"]):

        fieldname = (
            dt.name.lower()
            .replace(" ", "_")
            .replace("-", "_")
        )

        columns.append({
            "label": _(dt.name),
            "fieldname": fieldname,
            "fieldtype": "Int",
            "width": 120,
        })

    return columns


def get_data(filters):

    filters = filters or {}

    job_filters = {}

    if filters.get("from_date"):
        job_filters["creation"] = [">=", filters.get("from_date")]
        

    if filters.get("to_date"):
        if "creation" in job_filters:
            job_filters["creation"] = [
                "between",
                [filters.get("from_date"), filters.get("to_date")]
            ]
        else:
            job_filters["creation"] = ["<=", filters.get("to_date")]

    if filters.get("technician"):
        job_filters["assigned_technician"] = filters.get("technician")

    jobs = frappe.get_list(
        "Job Card",
        filters=job_filters,
        fields=[
            "assigned_technician",
            "status",
            "device_type",
            "final_amountc",
            "delivery_date",
            "diagnosis_date",
        ],
        limit_page_length=0,
    )

    technician_map = defaultdict(list)

    for job in jobs:
        technician_map[job.assigned_technician].append(job)

    data = []

    device_types = frappe.get_list(
        "Device Type",
        fields=["name"]
    )

    for technician, tech_jobs in technician_map.items():

        total_jobs = len(tech_jobs)

        completed = len([
            j for j in tech_jobs
            if j.status in ["Completed", "Delivered"]
        ])

        revenue = sum([
            j.final_amountc or 0
            for j in tech_jobs
        ])

        completion_rate = (
            (completed / total_jobs) * 100
            if total_jobs else 0
        )

        turnaround_total = 0
        turnaround_count = 0

        for j in tech_jobs:

            if j.delivery_date and j.diagnosis_date:

                turnaround_days = (
                    j.delivery_date - j.diagnosis_date
                ).days
                

                turnaround_total += turnaround_days
                turnaround_count += 1

        avg_turnaround = (
            turnaround_total / turnaround_count
            if turnaround_count else 0
        )

        row = {
            "technician": technician,
            "total_jobs": total_jobs,
            "completed": completed,
            "avg_turnaround_days": round(avg_turnaround, 2),
            "revenue": revenue,
            "completion_rate": round(completion_rate, 2),
        }

        # Dynamic Device Type Counts
        for dt in device_types:

            fieldname = (
                dt.name.lower()
                .replace(" ", "_")
                .replace("-", "_")
            )

            count = len([
                j for j in tech_jobs
                if j.device_type == dt.name and j.status in ["Completed", "Delivered"]
            ])

            row[fieldname] = count

        data.append(row)

    return data


def get_chart(data):

    return {
        "data": {
            "labels": [d["technician"] for d in data],
            "datasets": [
                {
                    "name": "Total Jobs",
                    "values": [d["total_jobs"] for d in data],
                },
                {
                    "name": "Completed",
                    "values": [d["completed"] for d in data],
                },
            ],
        },
        "type": "bar",
    }


def get_report_summary(data):

    total_jobs = sum([
        d["total_jobs"] for d in data
    ])

    total_revenue = sum([
        d["revenue"] for d in data
    ])

    best_technician = ""

    if data:
        best_tech = None
        max_rate = 0
        for tech in data:
            if tech["completion_rate"] > max_rate:
                max_rate = tech["completion_rate"]
                best_tech = tech
        if best_tech:
            best_technician = best_tech["technician"]

    return [
        {
            "label": _("Total Jobs"),
            "value": total_jobs,
            "indicator": "Blue",
        },
        {
            "label": _("Total Revenue"),
            "value": total_revenue,
            "indicator": "Green",
        },
        {
            "label": _("Best Technician"),
            "value": best_technician,
            "indicator": "Orange",
        },
    ]