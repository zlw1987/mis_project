<?php
require('validate.php');
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
<?php
    require('connection.php');
    $department = $_SESSION['department'];
    $projectId = $_GET['id'];  
    $query = "SELECT * FROM projects WHERE id = '".$projectId."'";
    $result = mysqli_query($conn, $query);

    if ($result && mysqli_num_rows($result) > 0) {
        $project = mysqli_fetch_assoc($result);
    } else {
        // Handle the case when the project is not found
        die("Project not found.");
    }
    // Close the database connection
    mysqli_close($conn);
?>
  <div class="container">
    <h2>Project Detail</h2>
    <form>
      <div class="row form-group">
        <div class="col-7">
          <label for="project-name">Project Name</label>
          <input type="text" id="project-name" value="<?php echo $project['project_name']; ?>" readonly>
        </div>
        <div class="col-5">
          <label for="date">Date</label>
          <input type="date" id="date" value="<?php echo $project['date']; ?>" readonly>
        </div>
      </div>
      <div class="row form-group">
        <div class="col-6">
          <label for="requestor">Requestor</label>
          <input type="text" id="requestor" value="<?php echo $project['requestor']; ?>" readonly>
        </div>
        <div class="col-6">
          <label for="requestor-department">Requestor Department</label>
          <input type="text" id="requestor-department" value="<?php echo $project['requestor_department']; ?>"
            readonly>
        </div>
      </div>
      <div class="form-group row">
        <div class="col-6">
          <label for="system">System</label>
          <input type="text" id="system" value="<?php echo $project['system']; ?>" readonly>
        </div>
        <div class="col-6">
          <label for="scope">Scope</label>
          <input type="text" id="scope" readonly><?php echo $project['scope']; ?></input>
        </div>
      </div>
      <div class="form-group row">
          <div class="related-info col-6">
            <label for="need-by-date">Need By Date</label>
            <input type="date" id="need-by-date" value="<?php echo $project['need_by_date']; ?>" readonly>
          </div>
          <div class="col-6">
            <label for="status">Status</label>
            <input type="text" id="status" value="<?php echo $project['status']; ?>" readonly>
          </div>
      </div>

      <div class="row form-group">
        <div class="col-12">
            <label for="description">Description</label>
            <textarea rows='6' id="description" readonly><?php echo $project['description']; ?></textarea>
        </div>
      </div>
      <div class="row form-group">
        <div class="related-info col-12">
          <label for="project-file">Project File</label>
          <?php if (empty( $project['file_path']) or is_null($project['file_path'])) {
            echo "&nbsp;&nbsp;No file uploaded!";}
            else {
          ?> 
          <a type='button' class='btn btn-info btn-sm' href="<?php echo $project['file_path']; ?>">Open file</a>
          <?php } ?>
        </div>
      </div>
      <hr class="solid">
      <div class="form-group">
        <label for="assign-to">Assign To</label>
        <input type="text" id="assign-to" value="<?php echo $project['assign_to']; ?>" readonly>
      </div>
      <div class="form-group">
        <label for="hours">Hours</label>
        <input type="text" id="hours" value="<?php echo $project['hours']; ?>" readonly>
      </div>
      <div class="form-group">
        <label for="etd">ETD</label>
        <?php
            if (empty( $project['file_path']) or is_null($project['file_path'])) { 
            echo "No ETD Provided!"; }
            else { ?>
            <input type="date" id="etd" value="<?php echo $project['etd']; ?>" readonly>
        <?php } ?>
      </div>
      <div class="form-group">
        <label for="dept-manager">Dept Manager</label>
        <input type="text" id="dept-manager" value="<?php echo $project['dept_manager']; ?>" readonly>
      </div>
      <div class="form-group">
        <label for="mis-manager">MIS Manager</label>
        <input type="text" id="mis-manager" value="<?php echo $project['mis_manager']; ?>" readonly>
      </div>
      <div class="form-group">
        <label for="mis-vp">MIS VP</label>
        <input type="text" id="mis-vp" value="<?php echo $project['mis_vp']; ?>" readonly>
      </div>
      <div class="form-group">
        <label for="approved-by">Approved By</label>
        <input type="text" id="approved-by" value="<?php echo $project['approved_by']; ?>" readonly>
      </div>
      <div class="form-group">
        <label for="approved-date">Approved Date</label>
        <input type="date" id="approved-date" value="<?php echo $project['approved_date']; ?>" readonly>
      </div>
      <div class="form-group">
        <label for="complete-date">Complete Date</label>
        <input type="date" id="complete-date" value="<?php echo $project['complete_date']; ?>" readonly>
      </div>
    </form>
  </div>
</body>

</html>
