USE mandate_health;

INSERT INTO customers (customer_id, name) VALUES
    ('C001', 'Aarav'),
    ('C002', 'Diya'),
    ('C003', 'Kabir'),
    ('C004', 'Meera'),
    ('C005', 'Vihaan')
ON DUPLICATE KEY UPDATE name = VALUES(name);

INSERT INTO subscriptions (subscription_id, customer_id, status) VALUES
    ('S001', 'C001', 'active'),
    ('S002', 'C002', 'active'),
    ('S003', 'C003', 'active'),
    ('S004', 'C004', 'active'),
    ('S005', 'C005', 'active')
ON DUPLICATE KEY UPDATE status = VALUES(status);

INSERT INTO payments
    (payment_id, subscription_id, customer_id, amount, status, payment_date, failure_reason)
VALUES
    ('P001','S001','C001',499,'success','2026-03-01 10:00:00',NULL),
    ('P002','S001','C001',499,'success','2026-04-01 10:00:00',NULL),
    ('P003','S001','C001',499,'success','2026-05-01 10:00:00',NULL),
    ('P004','S001','C001',499,'success','2026-06-01 10:00:00',NULL),
    ('P005','S001','C001',499,'success','2026-07-01 10:00:00',NULL),
    ('P006','S001','C001',499,'success','2026-08-01 10:00:00',NULL),
    ('P007','S002','C002',799,'success','2026-03-01 10:00:00',NULL),
    ('P008','S002','C002',799,'failed','2026-04-01 10:00:00','insufficient_balance'),
    ('P009','S002','C002',799,'success','2026-04-01 18:00:00',NULL),
    ('P010','S002','C002',799,'success','2026-05-01 10:00:00',NULL),
    ('P011','S002','C002',799,'success','2026-06-01 10:00:00',NULL),
    ('P012','S002','C002',799,'success','2026-07-01 10:00:00',NULL),
    ('P013','S003','C003',999,'success','2026-01-01 10:00:00',NULL),
    ('P014','S003','C003',999,'failed','2026-02-01 10:00:00','insufficient_balance'),
    ('P015','S003','C003',999,'success','2026-02-02 02:00:00',NULL),
    ('P016','S003','C003',999,'success','2026-03-01 10:00:00',NULL),
    ('P017','S003','C003',999,'failed','2026-04-01 10:00:00','bank_declined'),
    ('P018','S003','C003',999,'success','2026-04-02 02:00:00',NULL),
    ('P019','S003','C003',999,'failed','2026-07-01 10:00:00','insufficient_balance'),
    ('P020','S003','C003',999,'failed','2026-08-01 10:00:00','insufficient_balance'),
    ('P021','S004','C004',1299,'success','2026-03-01 10:00:00',NULL),
    ('P022','S004','C004',1299,'failed','2026-04-01 10:00:00','insufficient_balance'),
    ('P023','S004','C004',1299,'failed','2026-05-01 10:00:00','insufficient_balance'),
    ('P024','S004','C004',1299,'failed','2026-06-01 10:00:00','insufficient_balance'),
    ('P025','S004','C004',1299,'failed','2026-07-01 10:00:00','insufficient_balance'),
    ('P026','S004','C004',1299,'failed','2026-08-01 10:00:00','insufficient_balance'),
    ('P027','S005','C005',599,'failed','2026-03-01 10:00:00','insufficient_balance'),
    ('P028','S005','C005',599,'success','2026-03-01 23:00:00',NULL),
    ('P029','S005','C005',599,'failed','2026-04-01 10:00:00','insufficient_balance'),
    ('P030','S005','C005',599,'success','2026-04-01 23:00:00',NULL),
    ('P031','S005','C005',599,'failed','2026-05-01 10:00:00','insufficient_balance'),
    ('P032','S005','C005',599,'success','2026-05-01 23:00:00',NULL),
    ('P033','S005','C005',599,'failed','2026-06-01 10:00:00','insufficient_balance'),
    ('P034','S005','C005',599,'success','2026-06-01 23:00:00',NULL),
    ('P035','S005','C005',599,'failed','2026-07-01 10:00:00','insufficient_balance'),
    ('P036','S005','C005',599,'success','2026-07-01 23:00:00',NULL),
    ('P037','S005','C005',599,'failed','2026-08-01 10:00:00','insufficient_balance')
ON DUPLICATE KEY UPDATE
    amount = VALUES(amount),
    status = VALUES(status),
    payment_date = VALUES(payment_date),
    failure_reason = VALUES(failure_reason);

INSERT INTO payment_attempts
    (attempt_id, payment_id, subscription_id, attempt_number, attempt_time, status, failure_reason)
SELECT
    CONCAT('A', LPAD(CAST(SUBSTRING(payment_id, 2) AS UNSIGNED), 3, '0')),
    payment_id,
    subscription_id,
    1,
    payment_date,
    status,
    failure_reason
FROM payments
WHERE payment_id BETWEEN 'P001' AND 'P037'
ON DUPLICATE KEY UPDATE
    attempt_time = VALUES(attempt_time),
    status = VALUES(status),
    failure_reason = VALUES(failure_reason);
