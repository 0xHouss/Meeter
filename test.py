from datetime import datetime, timedelta

utc_diff = datetime.now() - datetime.utcnow()
utc = timedelta(hours=1)

utc = (utc - utc_diff)


print(datetime(2022, 11, 18, 19, 47, 30) + utc)