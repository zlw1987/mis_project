<?php
    require('validate.php');
    $id = $_SESSION['id'];
    $multi_department = false;
    require('connection.php');
    // Check the connection
    if ($conn->connect_error) {
        die("Connection failed: " . $conn->connect_error);
    }
    $sql = "SELECT d.id,d.name,mu.access_level FROM multi_department_user mu, department d where mu.employee=".$id." and d.id = mu.department";
    $result = mysqli_query($conn, $sql);
    if ($result && mysqli_num_rows($result) > 0) {
        $multi_department = true;
    }
    if ($_SERVER["REQUEST_METHOD"] == "POST"){
        $multi_dept = $_POST['multi_dept'];
        $pos = strpos($multi_dept, "-");
        $_SESSION['department'] = substr($multi_dept,0,$pos);
        $_SESSION['department_code'] = intval(substr($multi_dept,$pos+1));
        $pos = strpos($multi_dept, ".");
        $_SESSION['authorization'] = intval(substr($multi_dept,$pos+1));
    }
    // Close the database connection
    $conn->close();
?>

<!DOCTYPE html>
<html>

<head>
  <title>Landing Page</title>
  <!-- Include Bootstrap CSS -->
  <link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css">
  <link rel="stylesheet" href="style.css">
</head>

<body>
    <div class="container">
        <h3 class="text-center mt-5">AMAX Project Management System</h3>
        <div class="text-center mt-5">
            <a href="request.php" class="btn btn-primary btn-lg mb-3 d-block">New Request</a>
            <a href="show_projects.php" class="btn btn-primary btn-lg mb-3 d-block">Projects</a>
        </div>   
    <?php
        echo "<br />";
        echo "<div style='text-align:center'>";
            if ($multi_department){
                echo "You are in multiple departments and your current department is <b>".$_SESSION['department']."</b>.<br />Please select the department you would like to check:<br />";
                echo '<form method="POST" action="'.htmlspecialchars($_SERVER["PHP_SELF"]).'">';
                $result->data_seek(0);
                while ($multi_dp = $result->fetch_assoc()) {
                    echo '<button name="multi_dept" type="submit" value="'.$multi_dp['name'].'-'.$multi_dp['id'].'.'.$multi_dp['access_level'].'">'.$multi_dp['name'].'</button>';
                    echo '&nbsp;&nbsp;';
                }
                echo "</form>";
            }
        echo "</div>";
    ?>
    </div>
    <!-- Include Bootstrap JS -->
    <script src="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/js/bootstrap.min.js"></script>
</body>

</html>