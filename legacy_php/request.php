<?php
    require('validate.php');
    $user = $_SESSION['name'];
    $department = $_SESSION['department'];
    require('connection.php');
    $query = "SELECT * FROM options WHERE subject = 'project_type'";
    $project_type = $conn->query($query);
    $query = "SELECT * FROM options WHERE subject = 'file_type'";
    $file_type = $conn->query($query);
    $query = "SELECT * FROM department WHERE project = 'Y'";
    $project_department = $conn->query($query);
    if (!($project_type && mysqli_num_rows($project_type) > 0) or !($file_type && mysqli_num_rows($file_type) > 0) or !($project_department && mysqli_num_rows($project_department) > 0)) {
        // Handle the case when the project is not found
        die("Something went wrong. Please try again");
    }
    // Close the database connection
    mysqli_close($conn);
?>

<!DOCTYPE html>
<html>
<head>
    <title>Project Submission</title>
    <link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css">
    <link rel="stylesheet" href="style.css">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body>
    <div class="container">
        <a type='button' class='btn btn-info btn-sm mb-3' onclick="history.back()">Back</a>
        <h2>Request Submission Form</h2>
        <form action="submit_request.php" method="post" enctype="multipart/form-data">
            <div class="form-row">
                <div class="form-group">
                    <label for="project-name">*Project Name:</label>
                    <input type="text" id="project-name" name="project-name" required>
                </div>
                <div class="form-group">
                    <label for="date">*Date:</label>
                    <input type="date" id="date" name="date" style="width:50%" readonly="readonly">
                </div>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label for="requestor">*Requestor:</label>
                    <input type="text" id="requestor" name="requestor" value="<?php echo $user; ?>" readonly required>
                </div>
                <div class="form-group">
                    <label for="requestor-department">*Requestor Department:</label>
                    <input type="text" id="requestor-department" name="requestor-department"  value="<?php echo $department; ?>" readonly required>
                </div>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label for="type">*Request Type:</label>
                    <select id="type" name="type" required>
                        <option value="">--Make a selection--</option>
                        <?php
                            while ($type = $project_type->fetch_assoc()) {
                                echo "<option value='".$type["id"]."'>" . $type["name"] . "</option>";
                            }
                        ?>
                    </select>
                </div>
                <div class="form-group">
                    <label for="costomer">For Customer:</label>
                    <input type="text" id="customer" name="customer">
                </div>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label for="project_department">*Request to Department:</label>
                    <select id="project_department" name="project_department" style="width:35%" required>
                        <option value="">--Make a selection--</option>
                        <?php
                            while ($type = $project_department->fetch_assoc()) {
                                echo "<option value='".$type["id"]."'>" . $type["name"]. "</option>";
                            }
                        ?>
                    </select>
                </div>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label for="system">System:</label>
                    <input type="text" id="system" name="system">
                </div>
                <div class="form-group">
                    <label for="scope">Scope/Region:</label>
                    <textarea id="scope" name="scope" rows="2"></textarea>
                </div>
            </div>
            <div class="form-group">
                <label for="description">*Description:</label>
                <textarea id="description" name="description" rows="8" required></textarea>
            </div>
            <hr>
            <div class="form-row">
                <div class="form-group">
                    <label for="priority">*Priority(1 being the highest):</label>
                    <input type="number" id="priority" name="priority" style="width:20%" min="1" max="5" value="5" required>
                </div>
                <div class="form-group">
                    <label for="need-by-date">*Need By Date:</label>
                    <input type="date" id="need-by-date" name="need-by-date" style="width:50%" required>
                </div>
            </div>
            <hr>
            <div class="form-row">
                <div class="form-group">
                    <label for="file">Project File:</label>
                    <input type="file" id="file" name="file" accept=".zip,.rar,.doc,.txt,.msg,.pdf,.docx,.xls,.xlsx,.ppt,.pptx,.jpg,.jpeg,.png,.tif">
                </div>
                <div class="form-group">
                    <label for="file_type">File Type:</label>
                    <select id="file_type" name="file_type" style="width:40%">
                        <?php
                            while ($type = $file_type->fetch_assoc()) {
                                echo "<option value='".$type["id"]."'>" . $type["name"] . "</option>";
                            }
                        ?>
                    </select>
                </div>
            </div>
            <div class="form-group">
                <label for="file_desc">File Description:</label>
                <textarea id="file_desc" name="file_desc" rows="4"></textarea>
            </div>
            <div class="form-group">
                <i style="color:red;">* required fields</i><br />
                <button type="submit">Submit</button><br />
            </div>
        </form>

    </div>
    <script>
        let today = new Date();
        const offset = today.getTimezoneOffset();
        today = new Date(today.getTime() - (offset * 60 * 1000)).toISOString().split("T")[0];
        var defaultDay = new Date();
        defaultDay.setDate(defaultDay.getDate() + 30);
        defaultDay = defaultDay.toISOString().split("T")[0];
        document.getElementById("date").value = today;
        document.getElementById("need-by-date").value = defaultDay;
        document.getElementById("need-by-date").min = today;
    </script>
</body>
</html>
