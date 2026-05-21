<?php
    require('validate.php');

    // Check if the form is submitted
    if ($_SERVER["REQUEST_METHOD"] == "POST") {
    // Retrieve the form data
        $projectName = $_POST["project-name"];
        $date = $_POST["date"];
        $requestorDepartment = $_POST["requestor-department"];
        $requestor = $_POST["requestor"];
        $system = $_POST["system"];
        $scope = $_POST["scope"];
        $description = $_POST["description"];
        $needByDate = $_POST["need-by-date"];
        $customer = $_POST["customer"];
        $priority = $_POST["priority"];
        $file_type = $_POST["file_type"];
        $file_desc = $_POST["file_desc"];
        $project_department = $_POST["project_department"];
        $type = $_POST["type"];
        $targetFile = "";
        $id = $_SESSION['id'];
        $authorization = $_SESSION['authorization'];
        $department_code = $_SESSION['department_code'];
        $status = 9;

        require('connection.php');
        // check duplicate submission
        $sql = "SELECT count(*) as allcount FROM projects where project_name = '".$projectName."' and type = '". $type ."' and requestor = '".$id."' and status = 9";
        $result = mysqli_query($conn,$sql);
        $row = mysqli_fetch_array($result);
        $allcount = $row['allcount'];
        if($allcount == 0){ 
            $sql = "INSERT INTO projects (project_name, requestor, system, scope, description, need_by_date, customer, status,Priority,type,requestor_department,project_department )
                    VALUES ('$projectName', '$id', '$system', '$scope', '$description', '$needByDate', '$customer',$status,$priority,'$type',$department_code,$project_department)";
            if ($conn->query($sql) === TRUE) {
                $project = $conn->insert_id;
            } else {
                echo "Error submitting request: " . $conn->error;
                return;
            }
            //Generate Approval Requirements
            $approval = "";
            $approval_required = array (
                      array(0,$department_code,2),
                      array(0,$project_department,2),
                      array(0,$project_department,1),
                    ); 
            $approval_detail = array('Department Manager','Project Deparment Manager','Project Deparment VP');
            //Project Department manager approval is requred for all projects except for projects submitted by project department manager 
            if ($department_code != $project_department or ($department_code == $project_department && $authorization > 2)){
                $approval_required[1][0] = 1;
            }
            //Deparment manager approval requred except for projects submitted by Department manager or project department
            if ($authorization > 2 && $department_code != $project_department){ 
                $approval_required[0][0] = 1;
            }
            //Project Department VP approval required for all top Priority projects except projects submitted by project department VP
            if ($priority == 1 && ($department_code != $project_department or $authorization >1)){ 
                $approval_required[2][0] = 1;              
            }
            for ($i = 0; $i<count($approval_required);$i++){
                if ($approval_required[$i][0] == 1){
                    $sql = "INSERT INTO approval (department, access_level, status, project)
                            VALUES (".$approval_required[$i][1].",".$approval_required[$i][2].", 'N', ".$project.")"; 
                    if ($conn->query($sql) === false) {
                        echo "Connection Error: " . $conn->error;
                        return;
                    }
                    if ($approval == ""){
                        $approval .= $approval_detail[$i];
                    }else{
                        $approval .= ", " . $approval_detail[$i];
                    }
                }
            }
            if ($approval != ""){
                $approval .= "'s approval required.";
            }else{
                $status = 4;
            }
            //Process files
            if ($_FILES["file"]["size"]>0){
                // Handle the file upload
                $targetDirectory = "uploads/".$project; // Specify the directory to save the uploaded file
                $targetFile = $targetDirectory . basename($_FILES["file"]["name"]); // Get the file name
                if (move_uploaded_file($_FILES["file"]["tmp_name"], $targetFile)) {
                    // File upload success
                    echo "<p>File uploaded successfully. </p>";
                }else {
                    // File upload failed
                    echo "Sorry, there was an error uploading your file. <br>";
                }
                $sql = "INSERT INTO project_file (project, file_path, description, type,upload_by)
                            VALUES ('".$project."','".$targetFile."','".$file_desc."','".$file_type."', '".$id."')"; 
                if ($conn->query($sql) === false) {
                    echo "Connection Error: " . $conn->error;
                    return;
                }
            }
            //Project log
            $sql = "INSERT INTO project_log (project, type, description, add_by)
                    VALUES (".$project.",18, 'Request Submission', ".$id.")"; 
            if ($conn->query($sql) === false) {
                echo "Connection Error: " . $conn->error;
                return;
            }
        }else{
            echo "Something went wrong! Duplicate Request found!";
            $conn->close();
            return;
        }
        // Close the database connection
        $conn->close();
    }else{
    header('Location: error.php');  
    }
?>
<!DOCTYPE html>
<html>

<head>
  <title>Project Detail</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@4.3.1/dist/css/bootstrap.min.css" integrity="sha384-ggOyR0iXCbMQv3Xipma34MD+dH/1fQ784/j6cY/iJTQUOhcWr7x9JvoRxT2MZw1T" crossorigin="anonymous">
  <link rel="stylesheet" href="style.css">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  </style>
</head>
<body>
    <div class="container">
<?php
    if ($_SERVER["REQUEST_METHOD"] == "POST") {
?>
    <h3>Your project request submitted successfully</h3></ br></ br></ br></ br>
    <div style="margin-top:5%;text-align:left">
        <h4>Submitted Data:</h4>
        <p><strong>Project Name:</strong> <?php echo $projectName ?></p>
        <p><strong>Date:</strong> <?php echo $date ?> </p>
        <p><strong>Requestor:</strong> <?php echo $requestor ?> </p>
        <p><strong>Requestor Department:</strong> <?php echo $requestorDepartment ?> </p>
        <p><strong>Request Type:</strong> <?php echo $type ?> </p>
        <p><strong>priority:</strong> <?php echo $priority ?></p>
        <p><strong>System:</strong> <?php echo $system ?></p>
        <p><strong>Scope:</strong> <?php echo $scope ?></p>
        <p><strong>Customer:</strong> <?php echo $customer ?></p>
        <p><strong>Description:</strong> <?php echo $description ?></p>
        <p><strong>Need By Date:</strong> <?php echo $needByDate ?></p>
    </div>
<?php
    if ($approval != ""){
        echo "</ br></ br><p><i>".$approval."</i></p>";
    }
}
?>
    <a type='button' class='btn btn-info btn-sm m-3' href='show_projects.php'>Go to Projects</a>
    </div>
</body>
</html>