import csv
import io
from collections.abc import Iterable, Sequence

from fastapi import Response


def csv_response(
    filename: str, headers: Sequence[str], rows: Iterable[Sequence[object]]
) -> Response:
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
